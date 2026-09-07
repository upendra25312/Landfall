"""
Create the Landfall narrative-docs index pipeline on the FREE Azure AI Search tier:
data source (ADLS Gen2 -> raw/docs) -> skillset (split + embed, 512-dim) -> index -> indexer.

Uses Entra ID auth (no admin keys). The Search service's managed identity must have
Storage Blob Data Reader on the storage account and Cognitive Services OpenAI User on
the Foundry account - the Bicep grants both.

Env (from azd .azure/<env>/.env):
  AZURE_SEARCH_ENDPOINT
  AZURE_SEARCH_INDEX_NAME               (default: landfall-docs)
  AZURE_STORAGE_ACCOUNT
  AZURE_STORAGE_BLOB_ENDPOINT
  AZURE_OPENAI_ENDPOINT
  AZURE_OPENAI_EMBEDDING_DEPLOYMENT     (text-embedding-3-small)
  AZURE_RESOURCE_GROUP, AZURE_SUBSCRIPTION_ID
"""
import os

from azure.identity import DefaultAzureCredential
from azure.search.documents.indexes import SearchIndexerClient, SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex, SearchField, SearchFieldDataType, VectorSearch, VectorSearchProfile,
    HnswAlgorithmConfiguration, AzureOpenAIVectorizer, AzureOpenAIVectorizerParameters,
    SearchIndexerDataSourceConnection, SearchIndexerDataContainer, SearchIndexer,
    SearchIndexerSkillset, SplitSkill, AzureOpenAIEmbeddingSkill, InputFieldMappingEntry,
    OutputFieldMappingEntry, SearchIndexerIndexProjection, SearchIndexerIndexProjectionSelector,
    SearchIndexerIndexProjectionsParameters, IndexProjectionMode, FieldMapping,
)

DIM = 512
NAME = os.environ.get("AZURE_SEARCH_INDEX_NAME", "landfall-docs")
cred = DefaultAzureCredential()
endpoint = os.environ["AZURE_SEARCH_ENDPOINT"]
aoai = os.environ["AZURE_OPENAI_ENDPOINT"]
embed_deploy = os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")
sub = os.environ["AZURE_SUBSCRIPTION_ID"]
rg = os.environ["AZURE_RESOURCE_GROUP"]
acct = os.environ["AZURE_STORAGE_ACCOUNT"]

ix_client = SearchIndexClient(endpoint, cred)
er_client = SearchIndexerClient(endpoint, cred)

# ---- index ----
index = SearchIndex(
    name=NAME,
    fields=[
        SearchField(name="chunk_id", type=SearchFieldDataType.String, key=True,
                    sortable=True, analyzer_name="keyword"),
        SearchField(name="parent_id", type=SearchFieldDataType.String, filterable=True),
        SearchField(name="title", type=SearchFieldDataType.String, searchable=True),
        SearchField(name="chunk", type=SearchFieldDataType.String, searchable=True),
        SearchField(name="text_vector", type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                    vector_search_dimensions=DIM, vector_search_profile_name="hnsw"),
    ],
    vector_search=VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="hnsw")],
        profiles=[VectorSearchProfile(name="hnsw", algorithm_configuration_name="hnsw",
                                      vectorizer_name="aoai")],
        vectorizers=[AzureOpenAIVectorizer(
            vectorizer_name="aoai",
            parameters=AzureOpenAIVectorizerParameters(
                resource_url=aoai, deployment_name=embed_deploy, model_name="text-embedding-3-small"),
        )],
    ),
)
ix_client.create_or_update_index(index)
print(f"index: {NAME}")

# ---- data source (ADLS Gen2, folder raw/docs) ----
ds = SearchIndexerDataSourceConnection(
    name="landfall-docs-ds",
    type="adlsgen2",
    connection_string=(
        f"ResourceId=/subscriptions/{sub}/resourceGroups/{rg}/providers/"
        f"Microsoft.Storage/storageAccounts/{acct};"
    ),
    container=SearchIndexerDataContainer(name="raw", query="docs"),
)
er_client.create_or_update_data_source_connection(ds)
print("data source: landfall-docs-ds")

# ---- skillset: split -> embed -> project chunks into the index ----
skillset = SearchIndexerSkillset(
    name="landfall-docs-ss",
    skills=[
        SplitSkill(
            text_split_mode="pages", maximum_page_length=2000, page_overlap_length=500,
            inputs=[InputFieldMappingEntry(name="text", source="/document/content")],
            outputs=[OutputFieldMappingEntry(name="textItems", target_name="pages")],
        ),
        AzureOpenAIEmbeddingSkill(
            resource_url=aoai, deployment_name=embed_deploy, model_name="text-embedding-3-small",
            dimensions=DIM,
            context="/document/pages/*",
            inputs=[InputFieldMappingEntry(name="text", source="/document/pages/*")],
            outputs=[OutputFieldMappingEntry(name="embedding", target_name="text_vector")],
        ),
    ],
    index_projection=SearchIndexerIndexProjection(
        selectors=[SearchIndexerIndexProjectionSelector(
            target_index_name=NAME, parent_key_field_name="parent_id",
            source_context="/document/pages/*",
            mappings=[
                InputFieldMappingEntry(name="chunk", source="/document/pages/*"),
                InputFieldMappingEntry(name="text_vector", source="/document/pages/*/text_vector"),
                InputFieldMappingEntry(name="title", source="/document/metadata_storage_name"),
            ],
        )],
        parameters=SearchIndexerIndexProjectionsParameters(
            projection_mode=IndexProjectionMode.SKIP_INDEXING_PARENT_DOCUMENTS),
    ),
)
er_client.create_or_update_skillset(skillset)
print("skillset: landfall-docs-ss")

# ---- indexer (6-hourly) ----
indexer = SearchIndexer(
    name="landfall-docs-ixr",
    data_source_name="landfall-docs-ds",
    skillset_name="landfall-docs-ss",
    target_index_name=NAME,
    schedule={"interval": "PT6H"},
    field_mappings=[FieldMapping(source_field_name="metadata_storage_name", target_field_name="title")],
)
er_client.create_or_update_indexer(indexer)
er_client.run_indexer("landfall-docs-ixr")
print("indexer: landfall-docs-ixr (started)")

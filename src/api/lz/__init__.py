"""
Landing-zone design (PRD E3).

  from lz.design import design_landing_zone

`design_landing_zone` turns the client application portfolio + a server summary
into a client-specific CAF Azure Landing Zone — management groups, subscriptions,
hub-spoke VNets with an IP plan, policy set, identity, connectivity, DR, and a
regulated spoke when the portfolio carries a compliance scope. Deterministic and
pure: swap the portfolio and the topology changes (E3.2).

The output is a design document, not IaC. Hand it to the
`azure-enterprise-infra-planner` skill as a requirements doc to generate Bicep.
"""
from .design import design_landing_zone, assign_zone

__all__ = ["design_landing_zone", "assign_zone"]

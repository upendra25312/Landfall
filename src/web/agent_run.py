"""Nonblocking background response polling with best-effort remote cancellation."""
import asyncio
import logging
import time


async def run_response(client, kwargs, limits):
    response = None
    started = time.monotonic()
    try:
        async with asyncio.timeout(limits.runtime_seconds):
            response = await asyncio.to_thread(client.responses.create, **kwargs,
                                               background=True,
                                               max_tool_calls=limits.tool_calls,
                                               max_output_tokens=limits.output_tokens)
            while response.status in ('queued', 'in_progress'):
                await asyncio.sleep(1)
                response = await asyncio.to_thread(client.responses.retrieve, response.id)
            return response
    except TimeoutError:
        if response is not None and response.status in ('queued', 'in_progress'):
            try:
                await asyncio.wait_for(asyncio.to_thread(client.responses.cancel, response.id), 10)
            except Exception:
                logging.getLogger('landfall.web').exception('agent cancellation failed')
        raise TimeoutError(f'Assessment request exceeded {limits.runtime_seconds}s; check saved outputs before retrying') from None
    finally:
        logging.getLogger('landfall.web').debug('Agent wait ended after %.1fs', time.monotonic() - started)

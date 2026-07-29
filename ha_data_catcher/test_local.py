import asyncio
import logging
import json
from app.collectors.analytics_collector import AnalyticsCollector

logging.basicConfig(level=logging.DEBUG)

async def main():
    collector = AnalyticsCollector(
        matter_ws_url="ws://192.168.0.41:5580/ws",
        custom_storage_url="http://192.168.0.41:8100",
        webhook_url="https://script.google.com/macros/s/AKfycbwPzN2s-3x3x3x/exec"
    )
    # 1. Fetch matter nodes
    nodes = await collector.fetch_matter_nodes()
    print(f"Fetched {len(nodes)} nodes from Matter server.")
    
    # 2. Fetch custom metadata
    docks, snaps, rooms = collector.fetch_custom_metadata()
    print(f"Fetched {len(docks)} docks, {len(snaps)} snaps, {len(rooms)} rooms.")
    
    # 3. Just mock run_sync print to see if it crashes internally
    class MockEnricher:
        def resolve_matter_node_id(self, entity_id): return None
    collector.enricher = MockEnricher()
    
    # Run sync but intercept requests.post to just print
    import requests
    old_post = requests.post
    def mock_post(url, json, timeout):
        print("WEBHOOK JSON PAYLOAD:", json)
        return type('obj', (object,), {'status_code': 200})
    requests.post = mock_post
    
    await collector.run_sync("test_mac")

asyncio.run(main())

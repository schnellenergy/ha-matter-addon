import asyncio
import json
from app.collectors.analytics_collector import AnalyticsCollector

async def main():
    collector = AnalyticsCollector(matter_ws_url='ws://localhost:5580/ws')
    nodes = await collector.fetch_matter_nodes()
    with open('node_realtime.json', 'w') as f:
        json.dump(nodes, f, indent=2)

asyncio.run(main())

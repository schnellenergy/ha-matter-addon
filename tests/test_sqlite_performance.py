#!/usr/bin/env python3
"""
SQLite Performance Test for Custom Data Storage Add-on
Tests performance with large datasets to demonstrate scalability
"""

import requests
import json
import time
import random
import string
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

class SQLitePerformanceTest:
    def __init__(self, base_url="http://localhost:8100", api_key=None):
        self.base_url = base_url
        self.api_key = api_key
        self.headers = {'Content-Type': 'application/json'}
        if api_key:
            self.headers['X-API-Key'] = api_key
    
    def generate_test_data(self, count=1000):
        """Generate test data for performance testing"""
        categories = ['devices', 'users', 'analytics', 'config', 'history']
        device_types = ['light', 'fan', 'switch', 'sensor', 'camera']
        
        test_data = []
        for i in range(count):
            category = random.choice(categories)
            
            if category == 'devices':
                data = {
                    'key': f'device_{i:06d}',
                    'value': {
                        'name': f'Device {i}',
                        'type': random.choice(device_types),
                        'room': f'Room {random.randint(1, 20)}',
                        'online': random.choice([True, False]),
                        'last_seen': datetime.now().isoformat(),
                        'properties': {
                            'brightness': random.randint(0, 255),
                            'temperature': round(random.uniform(15.0, 30.0), 1),
                            'battery': random.randint(0, 100)
                        }
                    },
                    'category': category
                }
            elif category == 'users':
                data = {
                    'key': f'user_{i:06d}',
                    'value': {
                        'username': f'user{i}',
                        'email': f'user{i}@example.com',
                        'preferences': {
                            'theme': random.choice(['light', 'dark']),
                            'language': random.choice(['en', 'es', 'fr', 'de']),
                            'notifications': random.choice([True, False])
                        },
                        'last_login': datetime.now().isoformat()
                    },
                    'category': category
                }
            elif category == 'analytics':
                data = {
                    'key': f'event_{i:06d}',
                    'value': {
                        'event_type': random.choice(['button_press', 'state_change', 'error']),
                        'entity_id': f'device_{random.randint(1, 100)}',
                        'timestamp': datetime.now().isoformat(),
                        'value': random.randint(0, 1000),
                        'metadata': {
                            'source': 'mobile_app',
                            'user_id': f'user_{random.randint(1, 50)}'
                        }
                    },
                    'category': category
                }
            else:
                data = {
                    'key': f'config_{i:06d}',
                    'value': {
                        'setting_name': f'setting_{i}',
                        'setting_value': ''.join(random.choices(string.ascii_letters, k=20)),
                        'updated_at': datetime.now().isoformat()
                    },
                    'category': category
                }
            
            test_data.append(data)
        
        return test_data
    
    def test_bulk_insert(self, count=1000):
        """Test bulk insert performance"""
        print(f"\n📊 Testing bulk insert performance ({count} records)...")
        
        test_data = self.generate_test_data(count)
        
        start_time = time.time()
        success_count = 0
        
        for i, data in enumerate(test_data):
            try:
                response = requests.post(
                    f"{self.base_url}/api/data",
                    json=data,
                    headers=self.headers,
                    timeout=10
                )
                if response.status_code == 200:
                    success_count += 1
                
                if (i + 1) % 100 == 0:
                    elapsed = time.time() - start_time
                    rate = (i + 1) / elapsed
                    print(f"  Progress: {i + 1}/{count} ({rate:.1f} records/sec)")
                    
            except Exception as e:
                print(f"  Error inserting record {i}: {e}")
        
        end_time = time.time()
        total_time = end_time - start_time
        
        print(f"✅ Bulk insert completed:")
        print(f"   Records: {success_count}/{count}")
        print(f"   Time: {total_time:.2f} seconds")
        print(f"   Rate: {success_count/total_time:.1f} records/second")
        
        return success_count, total_time
    
    def test_concurrent_writes(self, count=100, threads=10):
        """Test concurrent write performance"""
        print(f"\n🔄 Testing concurrent writes ({count} records, {threads} threads)...")
        
        test_data = self.generate_test_data(count)
        
        def write_data(data):
            try:
                response = requests.post(
                    f"{self.base_url}/api/data",
                    json=data,
                    headers=self.headers,
                    timeout=10
                )
                return response.status_code == 200
            except:
                return False
        
        start_time = time.time()
        success_count = 0
        
        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = [executor.submit(write_data, data) for data in test_data]
            
            for future in as_completed(futures):
                if future.result():
                    success_count += 1
        
        end_time = time.time()
        total_time = end_time - start_time
        
        print(f"✅ Concurrent writes completed:")
        print(f"   Records: {success_count}/{count}")
        print(f"   Time: {total_time:.2f} seconds")
        print(f"   Rate: {success_count/total_time:.1f} records/second")
        print(f"   Threads: {threads}")
        
        return success_count, total_time
    
    def test_read_performance(self, count=100):
        """Test read performance"""
        print(f"\n📖 Testing read performance ({count} random reads)...")
        
        # Get list of available data
        response = requests.get(f"{self.base_url}/api/categories", headers=self.headers)
        if response.status_code != 200:
            print("❌ Failed to get categories")
            return 0, 0
        
        categories = response.json().get('categories', [])
        if not categories:
            print("❌ No categories found")
            return 0, 0
        
        start_time = time.time()
        success_count = 0
        
        for i in range(count):
            try:
                # Get random category data
                category = random.choice(categories)
                response = requests.get(
                    f"{self.base_url}/api/data/{category}",
                    headers=self.headers,
                    timeout=5
                )
                if response.status_code == 200:
                    success_count += 1
                    
            except Exception as e:
                print(f"  Error reading data {i}: {e}")
        
        end_time = time.time()
        total_time = end_time - start_time
        
        print(f"✅ Read performance test completed:")
        print(f"   Reads: {success_count}/{count}")
        print(f"   Time: {total_time:.2f} seconds")
        print(f"   Rate: {success_count/total_time:.1f} reads/second")
        
        return success_count, total_time
    
    def test_search_performance(self, count=50):
        """Test search performance"""
        print(f"\n🔍 Testing search performance ({count} searches)...")
        
        search_terms = ['device', 'user', 'light', 'fan', 'room', 'config', 'event']
        
        start_time = time.time()
        success_count = 0
        total_results = 0
        
        for i in range(count):
            try:
                search_term = random.choice(search_terms)
                response = requests.get(
                    f"{self.base_url}/api/search",
                    params={'q': search_term},
                    headers=self.headers,
                    timeout=10
                )
                if response.status_code == 200:
                    results = response.json()
                    success_count += 1
                    total_results += results.get('count', 0)
                    
            except Exception as e:
                print(f"  Error searching {i}: {e}")
        
        end_time = time.time()
        total_time = end_time - start_time
        
        print(f"✅ Search performance test completed:")
        print(f"   Searches: {success_count}/{count}")
        print(f"   Time: {total_time:.2f} seconds")
        print(f"   Rate: {success_count/total_time:.1f} searches/second")
        print(f"   Avg Results: {total_results/success_count:.1f} per search")
        
        return success_count, total_time
    
    def test_database_size(self):
        """Test database size and metadata"""
        print(f"\n📊 Testing database size and metadata...")
        
        try:
            response = requests.get(f"{self.base_url}/api/metadata", headers=self.headers)
            if response.status_code == 200:
                metadata = response.json()
                
                print(f"✅ Database metadata:")
                print(f"   Storage Type: {metadata.get('storage_type', 'unknown')}")
                print(f"   Total Values: {metadata.get('total_values', 0):,}")
                print(f"   Total Categories: {metadata.get('total_categories', 0)}")
                print(f"   Database Size: {metadata.get('database_size_mb', 0):.2f} MB")
                print(f"   Total Operations: {metadata.get('total_operations', 0):,}")
                print(f"   Categories: {', '.join(metadata.get('categories', []))}")
                
                if 'category_stats' in metadata:
                    print(f"   Category Statistics:")
                    for cat, stats in metadata['category_stats'].items():
                        print(f"     {cat}: {stats['count']} records")
                
                return metadata
            else:
                print(f"❌ Failed to get metadata: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"❌ Error getting metadata: {e}")
            return None
    
    def run_performance_suite(self):
        """Run complete performance test suite"""
        print("🚀 Starting SQLite Performance Test Suite")
        print("=" * 60)
        
        # Test database connection
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            if response.status_code != 200:
                print("❌ Add-on not accessible")
                return False
            
            health = response.json()
            print(f"✅ Add-on healthy (Storage: {health.get('storage_type', 'unknown')})")
            
        except Exception as e:
            print(f"❌ Cannot connect to add-on: {e}")
            return False
        
        # Run tests
        results = {}
        
        # Small dataset tests
        results['small_insert'] = self.test_bulk_insert(100)
        results['small_read'] = self.test_read_performance(50)
        
        # Medium dataset tests
        results['medium_insert'] = self.test_bulk_insert(1000)
        results['concurrent_writes'] = self.test_concurrent_writes(200, 5)
        results['medium_read'] = self.test_read_performance(100)
        results['search'] = self.test_search_performance(25)
        
        # Large dataset test (if requested)
        print(f"\n❓ Run large dataset test (10,000 records)? This may take several minutes.")
        user_input = input("Enter 'y' to continue or any other key to skip: ")
        if user_input.lower() == 'y':
            results['large_insert'] = self.test_bulk_insert(10000)
            results['large_read'] = self.test_read_performance(500)
            results['large_search'] = self.test_search_performance(100)
        
        # Final metadata
        metadata = self.test_database_size()
        
        # Summary
        print("\n" + "=" * 60)
        print("📊 Performance Test Summary")
        print("=" * 60)
        
        for test_name, (success, time_taken) in results.items():
            rate = success / time_taken if time_taken > 0 else 0
            print(f"{test_name:20}: {success:6} ops in {time_taken:6.2f}s ({rate:8.1f} ops/sec)")
        
        if metadata:
            print(f"\nFinal Database Size: {metadata.get('database_size_mb', 0):.2f} MB")
            print(f"Total Records: {metadata.get('total_values', 0):,}")
        
        print("\n🎉 Performance testing completed!")
        return True

if __name__ == "__main__":
    import sys
    
    # Default configuration
    base_url = "http://localhost:8100"
    api_key = None
    
    # Parse command line arguments
    if len(sys.argv) > 1:
        base_url = sys.argv[1]
    if len(sys.argv) > 2:
        api_key = sys.argv[2]
    
    # Run performance tests
    tester = SQLitePerformanceTest(base_url, api_key)
    success = tester.run_performance_suite()
    
    sys.exit(0 if success else 1)

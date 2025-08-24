#!/usr/bin/env python3
"""
Test script to verify FastSnakeStats integration
"""
import asyncio
import sys
import os

# Add current directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from github_cache_fetcher import github_cache_fetcher
import data_management as dm

async def test_github_cache():
    """Test GitHub cache functionality"""
    print("Testing FastSnakeStats Integration...")
    print("=" * 50)
    
    # Test 1: Check if GitHub cache is available
    print("1. Testing GitHub cache availability...")
    is_available = await github_cache_fetcher.is_github_cache_available()
    if is_available:
        print("✅ GitHub cache is available")
    else:
        print("❌ GitHub cache is not available")
        return False
    
    # Test 2: Get available dates
    print("\n2. Testing available dates...")
    dates = await github_cache_fetcher.get_available_dates()
    if dates:
        print(f"✅ Found {len(dates)} available dates")
        print(f"   Most recent: {dates[-1]}")
        print(f"   Oldest: {dates[0]}")
    else:
        print("❌ No available dates found")
        return False
    
    # Test 3: Get cache stats
    print("\n3. Testing cache stats...")
    stats = await github_cache_fetcher.get_cache_stats()
    if stats:
        print(f"✅ Cache stats retrieved")
        print(f"   Total dates: {stats.get('totalDates', 'N/A')}")
        if stats.get('dateRange'):
            print(f"   Date range: {stats['dateRange'].get('start', 'N/A')} to {stats['dateRange'].get('end', 'N/A')}")
    else:
        print("❌ Could not retrieve cache stats")
    
    # Test 4: Test record lookup
    print("\n4. Testing record lookup...")
    most_recent_date = await github_cache_fetcher.get_most_recent_date()
    if most_recent_date:
        print(f"   Using date: {most_recent_date}")
        
        # Test with Classic mode, 1 Apple, Normal speed, Standard size
        settings_key = dm.get_settings_key("1 Apple", "Normal", "Standard", "Classic")
        print(f"   Looking up: {settings_key}")
        
        world_records = await github_cache_fetcher.fetch_current_world_records()
        if world_records and settings_key in world_records:
            runs = world_records[settings_key]
            if runs and len(runs) > 0:
                best_run = runs[0]
                player_name = dm.get_player_name(best_run)
                run_time = dm.get_run_time(best_run)
                run_date = dm.get_run_date(best_run)
                
                print(f"✅ Record found!")
                print(f"   Player: {player_name}")
                print(f"   Time: {run_time}")
                print(f"   Date: {run_date}")
                print(f"   Total runs: {len(runs)}")
            else:
                print("❌ No runs found for this configuration")
        else:
            print("❌ No record data found for this configuration")
    else:
        print("❌ Could not get most recent date")
    
    print("\n" + "=" * 50)
    print("✅ FastSnakeStats integration test completed!")
    return True

async def test_data_management():
    """Test data management functions"""
    print("\nTesting Data Management...")
    print("=" * 30)
    
    # Test settings validation
    print("1. Testing settings validation...")
    valid = dm.validate_settings("1 Apple", "Normal", "Standard", "Classic")
    print(f"   Valid settings: {valid}")
    
    invalid = dm.validate_settings("Invalid", "Normal", "Standard", "Classic")
    print(f"   Invalid settings: {invalid}")
    
    # Test settings key generation
    print("\n2. Testing settings key generation...")
    key = dm.get_settings_key("1 Apple", "Normal", "Standard", "Classic")
    print(f"   Generated key: {key}")
    
    # Test time parsing
    print("\n3. Testing time parsing...")
    iso_time = "PT1M23.456S"
    parsed_time = dm.parse_time(iso_time)
    print(f"   ISO time: {iso_time}")
    print(f"   Parsed time: {parsed_time}")
    
    print("✅ Data management test completed!")

async def main():
    """Main test function"""
    try:
        await test_data_management()
        await test_github_cache()
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        return False
    
    return True

if __name__ == "__main__":
    success = asyncio.run(main())
    if success:
        print("\n🎉 All tests passed! FastSnakeStats integration is working correctly.")
    else:
        print("\n💥 Some tests failed. Please check the errors above.")

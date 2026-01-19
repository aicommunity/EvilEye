#!/usr/bin/env python3

import sys
import os
sys.path.append('.')

def debug_journal_data():
    """Debug journal data processing"""
    
    print("=== Debug Journal Data ===")
    
    try:
        from evileye.visualization_modules.journal_data_source_json import JsonLabelJournalDataSource
        
        ds = JsonLabelJournalDataSource('EvilEyeData')
        
        # Get raw data without sorting
        events = ds.fetch(0, 5, {}, [])  # Empty sort list
        
        print(f"Total events fetched: {len(events)}")
        
        for i, ev in enumerate(events):
            print(f"\nEvent {i+1}:")
            print(f"  event_id: {ev.get('event_id', 'N/A')}")
            print(f"  event_type: {ev.get('event_type', 'N/A')}")
            print(f"  ts: {ev.get('ts', 'N/A')}")
            print(f"  source_id: {ev.get('source_id', 'N/A')}")
            print(f"  source_name: {ev.get('source_name', 'N/A')}")
            print(f"  object_id: {ev.get('object_id', 'N/A')}")
            print(f"  class_id: {ev.get('class_id', 'N/A')}")
            print(f"  class_name: {ev.get('class_name', 'N/A')}")
            print(f"  frame_id: {ev.get('frame_id', 'N/A')}")
            print(f"  image_filename: {ev.get('image_filename', 'N/A')}")
            print(f"  bounding_box: {ev.get('bounding_box', 'N/A')}")
            print(f"  confidence: {ev.get('confidence', 'N/A')}")
            print(f"  date_folder: {ev.get('date_folder', 'N/A')}")
        
        # Check found vs lost separation
        print(f"\n=== Event Type Separation ===")
        found_events = ds.fetch(0, 3, {'event_type': 'found'}, [])
        lost_events = ds.fetch(0, 3, {'event_type': 'lost'}, [])
        
        print(f"Found events: {len(found_events)}")
        print(f"Lost events: {len(lost_events)}")
        
        if found_events:
            print(f"First found event type: {found_events[0].get('event_type')}")
            print(f"First found timestamp: {found_events[0].get('ts')}")
        
        if lost_events:
            print(f"First lost event type: {lost_events[0].get('event_type')}")
            print(f"First lost timestamp: {lost_events[0].get('ts')}")
        
        ds.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_journal_data()





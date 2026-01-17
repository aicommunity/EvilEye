#!/usr/bin/env python3

import sys
import os
sys.path.append('.')

def debug_journal_issues():
    """Debug journal issues"""
    
    print("=== Debug Journal Issues ===")
    
    try:
        from evileye.visualization_modules.journal_data_source_json import JsonLabelJournalDataSource
        
        ds = JsonLabelJournalDataSource('EvilEyeData')
        
        # Get sample data
        events = ds.fetch(0, 3, {}, [])
        
        print(f"\n📊 Raw Events Data:")
        for i, ev in enumerate(events):
            print(f"   Event {i+1}:")
            print(f"     event_type: {ev.get('event_type')}")
            print(f"     ts: {ev.get('ts')}")
            print(f"     object_id: {ev.get('object_id')}")
            print(f"     image_filename: {ev.get('image_filename')}")
            print(f"     date_folder: {ev.get('date_folder')}")
        
        # Test grouping logic
        print(f"\n🔧 Testing Grouping Logic:")
        grouped_events = {}
        for ev in events:
            object_id = ev.get('object_id')
            if object_id not in grouped_events:
                grouped_events[object_id] = {'found': None, 'lost': None}
            
            if ev.get('event_type') == 'found':
                grouped_events[object_id]['found'] = ev
            elif ev.get('event_type') == 'lost':
                grouped_events[object_id]['lost'] = ev
        
        print(f"   Grouped events: {len(grouped_events)}")
        for object_id, events_data in grouped_events.items():
            print(f"     Object {object_id}:")
            print(f"       Found: {events_data['found'] is not None}")
            print(f"       Lost: {events_data['lost'] is not None}")
            
            if events_data['found']:
                print(f"       Found ts: {events_data['found'].get('ts')}")
                print(f"       Found image: {events_data['found'].get('image_filename')}")
            
            if events_data['lost']:
                print(f"       Lost ts: {events_data['lost'].get('ts')}")
                print(f"       Lost image: {events_data['lost'].get('image_filename')}")
        
        # Test row data creation
        print(f"\n📋 Testing Row Data Creation:")
        for object_id, events_data in grouped_events.items():
            found_event = events_data['found']
            lost_event = events_data['lost']
            
            base_event = found_event or lost_event
            if not base_event:
                continue
            
            row_data = {
                'event': f"Object {object_id}",
                'time': found_event.get('ts') if found_event else '',
                'time_lost': lost_event.get('ts') if lost_event else '',
                'information': f"Object Id={object_id}; class: {base_event.get('class_name', base_event.get('class_id', ''))}; conf: {base_event.get('confidence', 0):.2f}",
                'preview': found_event.get('image_filename') if found_event else '',
                'lost_preview': lost_event.get('image_filename') if lost_event else '',
                'found_event': found_event,
                'lost_event': lost_event
            }
            
            print(f"     Row data for Object {object_id}:")
            print(f"       event: {row_data['event']}")
            print(f"       time: {row_data['time']}")
            print(f"       time_lost: {row_data['time_lost']}")
            print(f"       information: {row_data['information']}")
            print(f"       preview: {row_data['preview']}")
            print(f"       lost_preview: {row_data['lost_preview']}")
        
        ds.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_journal_issues()


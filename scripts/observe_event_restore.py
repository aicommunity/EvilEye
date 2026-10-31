"""Record the one-hour and 24-hour acceptance windows without modifying pipeline state."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', type=Path, required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--duration', type=float, default=86400)
    parser.add_argument('--interval', type=float, default=60)
    args = parser.parse_args()
    import psycopg2
    from evileye.core.runtime_identity import redact
    creds = json.loads((args.site/'credentials.json').read_text())['database']
    path = args.site/'monitor/event_restore_observation.jsonl'
    started = time.time()
    since = datetime.fromtimestamp(started)
    hourly_written = False
    config_path = args.site/'configs/poly-cameras-gst.json'
    import hashlib
    config_hash = hashlib.sha256(config_path.read_bytes()).hexdigest()
    while True:
        now = time.time()
        row = dict(observed_at=now, observation_started_at=started,
                   elapsed_sec=round(now-started), phase='observing')
        if now-started >= 3600 and not hourly_written:
            row['phase'] = 'one_hour'
            hourly_written = True
        if now-started >= args.duration:
            row['phase'] = 'completed'
        try:
            heartbeat = json.loads((args.site/'monitor/event_heartbeat.json').read_text())
            row.update(heartbeat_age_sec=round(now-heartbeat['updated_at'], 1),
                       pid=heartbeat['pid'], identity=heartbeat['identity'],
                       failures=list(heartbeat.get('failures') or []),
                       components=heartbeat.get('components'))
            if row['heartbeat_age_sec'] > 30:
                row['failures'].append('heartbeat_stale')
            if not heartbeat['identity']['git_sha'].startswith(args.revision):
                row['failures'].append('unexpected_revision')
            if hashlib.sha256(config_path.read_bytes()).hexdigest() != config_hash:
                row['failures'].append('configuration_changed')
            with psycopg2.connect(host=creds['host_name'], port=creds['port'],
                dbname=creds['database_name'], user=creds['user_name'], password=creds['password'],
                connect_timeout=5) as connection:
                connection.set_session(readonly=True)
                with connection.cursor() as cursor:
                    cursor.execute("SET statement_timeout='10000ms'")
                    cursor.execute('SELECT source_id,count(*),max(time_entered),max(time_left) '
                        'FROM zone_events WHERE time_entered >= %s GROUP BY source_id', (since,))
                    row['zone_events_since_start'] = cursor.fetchall()
                    cursor.execute('SELECT source_id,count(*),max(time_stamp) FROM objects '
                        'WHERE time_stamp >= %s GROUP BY source_id', (since,))
                    row['objects_since_start'] = cursor.fetchall()
        except Exception as exc:
            row.setdefault('failures', []).append(f'{type(exc).__name__}: {exc}')
        with path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(redact(row), default=str)+'\n')
        if row['phase'] == 'completed':
            return
        time.sleep(max(1, min(args.interval, args.duration-(time.time()-started))))


if __name__ == '__main__':
    main()

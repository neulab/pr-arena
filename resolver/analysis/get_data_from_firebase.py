"""
Firebase Data Extraction Script

This module connects to Firebase Firestore and extracts data from issue_collection,
writing the results to dated output files in the data directory.

Usage:
    python get_data_from_firebase.py

Output:
    Creates a file in ./data/ named with the current date (YYYY-MM-DD.txt)
    containing the query results and observations.

Dependencies:
    - firebase_admin: Firebase Admin SDK for Python
    - datetime: For timestamp generation

Configuration:
    Requires 'data/firebase_config.json' in the same directory as this script.
"""

from datetime import datetime
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, firestore


def initialize_firebase(config_path: str = 'data/firebase_config.json') -> firestore.Client:
    if not firebase_admin._apps:
        cred = credentials.Certificate(config_path)
        firebase_admin.initialize_app(cred)
    return firestore.client()


def create_output_file(data_dir: str = 'resolver/analysis/data') -> tuple[Path, str]:
    output_dir = Path(data_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    current_datetime = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    output_file = output_dir / f'{current_datetime}.txt'
    return output_file, current_datetime


def write_header(file_handle, date_str: str, query_description: str = ''):
    file_handle.write(f'Date: {date_str}\n')
    file_handle.write('=' * 80 + '\n')
    if query_description:
        file_handle.write(f'Query: {query_description}\n')
        file_handle.write('=' * 80 + '\n')
    file_handle.write('\n')


def write_observations(file_handle, observations: list[str]):
    file_handle.write('OBSERVATIONS:\n')
    file_handle.write('-' * 80 + '\n')
    for i, obs in enumerate(observations, 1):
        file_handle.write(f'{i}. {obs}\n')
    file_handle.write('\n')


def query_and_write_data(db: firestore.Client, output_file: Path, limit: int = 5000):
    observations = []

    with open(output_file, 'w') as f:
        # Write header
        current_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        write_header(f, current_date, f'Issue collection query (limit: {limit})')

        # Query issue_collection
        print(f'Querying issue_collection (limit: {limit})...')
        issues_ref = db.collection('issue_collection').limit(limit)
        issues = issues_ref.stream()
        issue_count = 0
        status_counts = {'pending': 0, 'completed': 0, 'other': 0}
        owners_found = set()

        f.write('QUERY RESULTS:\n')
        f.write('-' * 80 + '\n')

        try:
            for issue in issues:
                issue_count += 1
                issue_data = issue.to_dict()

                f.write(f'\n[{issue_count}] Document ID: {issue.id}\n')

                # Extract and write key fields
                issue_owner = issue_data.get('owner', 'N/A')
                owners_found.add(issue_owner)
                issue_number = issue_data.get('issue_number', 'N/A')
                issue_title = issue_data.get('issue_title', 'N/A')
                repo_url = issue_data.get('repo_url', 'N/A')
                status = issue_data.get('status', 'unknown')
                winner = issue_data.get('winner', 'N/A')
                created_at = issue_data.get('createdAt', 'N/A')

                # Count statuses
                if status == 'pending':
                    status_counts['pending'] += 1
                elif status == 'completed':
                    status_counts['completed'] += 1
                else:
                    status_counts['other'] += 1

                f.write(f'  Owner: {issue_owner}\n')
                f.write(f'  Repo URL: {repo_url}\n')
                f.write(f'  Issue Number: {issue_number}\n')
                f.write(f'  Issue Title: {issue_title}\n')
                f.write(f'  Status: {status}\n')
                f.write(f'  Winner: {winner}\n')
                f.write(f'  Created At: {created_at}\n')

                # Write model information if available
                if 'models' in issue_data:
                    models = issue_data['models']
                    if 'modelA' in models:
                        f.write(f'  Model A: {models["modelA"].get("modelName", "N/A")}\n')
                        f.write(f'    - Success: {models["modelA"].get("success", "N/A")}\n')
                        f.write(f'    - Duration: {models["modelA"].get("duration", "N/A")}\n')
                    if 'modelB' in models:
                        f.write(f'  Model B: {models["modelB"].get("modelName", "N/A")}\n')
                        f.write(f'    - Success: {models["modelB"].get("success", "N/A")}\n')
                        f.write(f'    - Duration: {models["modelB"].get("duration", "N/A")}\n')

                # Progress indicator
                if issue_count % 10 == 0:
                    print(f'  Processed {issue_count} records...')

        except Exception as e:
            error_msg = f'Error during query: {str(e)}'
            f.write(f'\nERROR: {error_msg}\n')
            observations.append(error_msg)

        # Generate observations
        observations.append(f'Total issues retrieved: {issue_count}')
        observations.append(f'Unique owners found: {len(owners_found)} ({", ".join(sorted(owners_found))})')
        observations.append(f'Status breakdown - Pending: {status_counts["pending"]}, Completed: {status_counts["completed"]}, Other: {status_counts["other"]}')

        if issue_count == 0:
            observations.append('No issues found in issue_collection')
        elif issue_count < limit:
            observations.append(f'Retrieved all available records ({issue_count} total)')
        else:
            observations.append(f'Limit of {limit} records reached - more data may be available')

        # Write observations
        f.write('\n')
        write_observations(f, observations)

    print(f'✓ Data written to: {output_file}')
    print(f'✓ Total records: {issue_count}')
    print(f'✓ Status breakdown: {status_counts}')


def main():
    print('Starting Firebase data extraction...')
    output_file = None
    try:
        # Create output file first
        print('Creating output file...')
        output_file, _ = create_output_file()
        print(f'✓ Output file path: {output_file}')

        # Initialize Firebase
        print('Initializing Firebase connection...')
        db = initialize_firebase('resolver/analysis/data/firebase_config.json')
        print('✓ Firebase connected successfully')

        # Query and write data (limit to 100 records)
        query_and_write_data(db, output_file, limit=5000)

        print('\n✓ Data extraction completed successfully!')

    except Exception as e:
        print(f'\n✗ Error: {str(e)}')
        import traceback
        traceback.print_exc()

        # Try to write error to file if possible
        if output_file:
            try:
                with open(output_file, 'w') as f:
                    f.write(f'ERROR: {str(e)}\n')
                    f.write(traceback.format_exc())
                print(f'Error written to: {output_file}')
            except:
                pass
        raise


if __name__ == '__main__':
    main()
import pytest
import asyncio
import os
import yaml
from deepdiff import DeepDiff
from perf.perf import run_perf
from src.manifest import read_migration_manifest
def clean_test_results(test_results):
    cleaned_results = []

    for test_result in test_results:
        cleaned_test_result = {
            'test_version': test_result['test_version'],
            'test_edition': test_result.get('test_edition'),
            'cases': []
        }

        for case in test_result['cases']:
            cleaned_case = {
                'case_name': case['case_name'],
                'explain_results': [],
                'timing_results': []
            }

            # Cleaning explain_results
            for explain_result in case.get('explain_results', []):
                cleaned_explain_result = {
                    'query': explain_result['query'],
                    'result': explain_result['result'],
                    'matched_expected_file': explain_result.get('matched_expected_file')
                }
                cleaned_case['explain_results'].append(cleaned_explain_result)

            # Cleaning timing_results
            for timing_result in case.get('timing_results', []):
                cleaned_timing_result = {
                    'query': timing_result['query'],
                    'result': timing_result['result'],
                    'status': timing_result.get('status')
                }
                cleaned_case['timing_results'].append(cleaned_timing_result)

            # # If pre_hook_result
            # if 'pre_hook_result' in case:
            #     cleaned_case['pre_hook_result'] = case['pre_hook_result']
            #
            # # If post_hook_result
            # if 'post_hook_result' in case:
            #     cleaned_case['post_hook_result'] = case['post_hook_result']

            cleaned_test_result['cases'].append(cleaned_case)

        cleaned_results.append(cleaned_test_result)

    return cleaned_results

@pytest.mark.asyncio
async def test_run_perf():
    """
    NEXUS_USER=<YOUR_USERNAME> NEXUS_USER_PASSWORD=<YOUR_PASSWD> NEXUS_URL=nexus-dev.*.com venv/bin/pytest -v tests/test_perf.py
    """
    scenario_path = 'tests/perf_test'
    manifest_path = os.path.join(scenario_path, 'conf.yaml')

    with open(manifest_path, 'r') as f:
        manifest = read_migration_manifest(f)

    test_results = await run_perf(manifest, scenario_path)

    cleaned_test_results = clean_test_results(test_results)

    results_dir = os.path.join('tests', 'perf_test', 'results')
    os.makedirs(results_dir, exist_ok=True)

    results_conf_path = os.path.join(results_dir, 'conf.yaml')

    with open(results_conf_path, 'w') as f:
        yaml.dump({'test_results': cleaned_test_results}, f, sort_keys=False)

    print(f"Test results saved to {results_conf_path}")

    expected_results_path = os.path.join('tests', 'perf_test', 'expected', 'conf.yaml')

    # Comparing results
    compare_results(expected_results_path, results_conf_path)

def compare_results(expected_results_path, actual_results_path):

    with open(expected_results_path, 'r') as f:
        expected_results = yaml.safe_load(f)

    with open(actual_results_path, 'r') as f:
        actual_results = yaml.safe_load(f)

    diff = DeepDiff(expected_results, actual_results, significant_digits=5)

    if not diff:
        print("Test passed: Actual results match expected results.")
    else:
        print("Test failed: Actual results do not match expected results.")
        print("Differences:")
        print(diff)

    assert not diff, "Actual results do not match expected results."

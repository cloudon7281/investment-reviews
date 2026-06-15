#!/usr/bin/env python3
"""Create semver tag and close linked issue on PR merge. Set SKIP_TAG=true to skip tagging (docs repos)."""
import json, os, re, urllib.request, urllib.error
from datetime import datetime, timezone

TOKEN    = os.environ['TOKEN']
API_BASE = os.environ['API_BASE']
REPO     = os.environ['REPO']
PR_NUM   = os.environ['PR_NUMBER']
SKIP_TAG = os.environ.get('SKIP_TAG', '').lower() == 'true'


def gitea(method, path, body=None):
    url  = f'{API_BASE}/repos/{REPO}/{path}'
    data = json.dumps(body).encode() if body else None
    req  = urllib.request.Request(url, data=data, headers={
        'Authorization': f'token {TOKEN}',
        'Content-Type':  'application/json',
    }, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        return e.code, {}


_, pr = gitea('GET', f'pulls/{PR_NUM}')

if not SKIP_TAG:
    # 0. If deploy/service.yaml changed, re-register BEFORE tagging so the deploy lands on
    #    a fresh registry (tier2-project#47). Register and deploy stay decoupled — this only
    #    sequences them. A registration failure withholds the tag (no broken deploy). Rollout-
    #    safe: only active where REGISTRARD_URL is configured; otherwise behaviour is unchanged.
    REGISTRARD_URL = os.environ.get('REGISTRARD_URL', '')
    REGISTRARD_SECRET = os.environ.get('REGISTRARD_SECRET', '')
    _, files = gitea('GET', f'pulls/{PR_NUM}/files')
    changed = [f.get('filename') for f in (files if isinstance(files, list) else [])]
    if 'deploy/service.yaml' in changed and REGISTRARD_URL:
        print('service.yaml changed -> re-registering via registrard before tagging')
        req = urllib.request.Request(
            REGISTRARD_URL,
            data=json.dumps({'repo': REPO}).encode(),
            method='POST',
            headers={'Authorization': f'Bearer {REGISTRARD_SECRET}', 'Content-Type': 'application/json'},
        )
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                print(f'registrard: {json.loads(r.read() or b"{}")}')
        except urllib.error.HTTPError as e:
            detail = e.read().decode('utf-8', 'replace')
            raise SystemExit(f'registrard re-register FAILED (HTTP {e.code}): {detail} -- not tagging; deploy blocked')
        except Exception as e:
            raise SystemExit(f'registrard call failed: {e} -- not tagging; deploy blocked')
    elif 'deploy/service.yaml' in changed:
        print('NOTE: service.yaml changed but REGISTRARD_URL unset -- tagging anyway; '
              'ensure the service was re-registered manually (tier2-project#47).')

    # 1. Determine version bump from PR labels
    labels = [l['name'] for l in pr.get('labels', [])]
    print(f'Labels: {labels}')
    bump = 'minor' if 'enhancement' in labels else 'patch'
    print(f'Bump: {bump}')

    # 2. Find latest semver tag and compute next
    _, tags_data = gitea('GET', 'tags?limit=50')
    tags_list = tags_data if isinstance(tags_data, list) else []
    semver = [t['name'] for t in tags_list
              if re.fullmatch(r'v\d+\.\d+\.\d+', t.get('name', ''))]
    latest = (max(semver, key=lambda t: [int(x) for x in t[1:].split('.')])
              if semver else 'v0.0.0')
    print(f'Latest: {latest}')

    major, minor, patch = (int(x) for x in latest[1:].split('.'))
    if bump == 'minor':
        minor += 1; patch = 0
    else:
        patch += 1
    next_tag = f'v{major}.{minor}.{patch}'
    print(f'Next: {next_tag}')

    # 3. Create tag on HEAD of main (idempotent — 409 = already exists)
    _, branch = gitea('GET', 'branches/main')
    sha = branch['commit']['id']
    status, _ = gitea('POST', 'tags', {'tag_name': next_tag, 'target': sha, 'message': next_tag})
    if status == 201:
        print(f'Tagged: {next_tag}')
    elif status == 409:
        print(f'Tag {next_tag} already exists, skipping')
    else:
        raise SystemExit(f'Tagging failed: HTTP {status}')
else:
    next_tag = None
    print('SKIP_TAG=true — skipping semver bump and tag creation')

# 4. Close linked issue if PR body contains Closes/Fixes #N
pr_body = pr.get('body') or ''
m = re.search(r'(?:closes|fixes)\s+#(\d+)', pr_body, re.IGNORECASE)
if not m:
    print('No Closes/Fixes reference — issue update skipped')
    raise SystemExit(0)

issue_num = m.group(1)
print(f'Linked issue: #{issue_num}')

ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

_, issue = gitea('GET', f'issues/{issue_num}')
old_body = issue.get('body') or ''

fixed_in   = next_tag if next_tag else f'PR #{PR_NUM}'
close_note = f'Merged PR #{PR_NUM} and tagged {next_tag}.' if next_tag else f'Merged PR #{PR_NUM}.'

if re.search(r'\*\*Fixed in:\*\*\s*\(pending\)', old_body):
    new_body = re.sub(r'\*\*Fixed in:\*\*\s*\(pending\)', f'**Fixed in:** {fixed_in}', old_body)
else:
    new_body = f'**Fixed in:** {fixed_in}\n\n' + old_body

new_body = new_body.rstrip() + (
    f'\n\n---\n**{ts} — auto-closed by auto-tag-on-merge**\n{close_note}\n'
)

status, _ = gitea('PATCH', f'issues/{issue_num}', {'body': new_body, 'state': 'closed'})
print(f'Issue #{issue_num}: PATCH {status}')

if next_tag:
    # Create release (idempotent — 409/422 = already exists)
    status, _ = gitea('POST', 'releases', {
        'tag_name': next_tag,
        'name':     next_tag,
        'body':     f'Merged PR #{PR_NUM}, closes #{issue_num}.',
    })
    if status == 201:
        print(f'Release {next_tag} created')
    elif status in (409, 422):
        print(f'Release {next_tag} already exists, skipping')
    else:
        print(f'Release creation: HTTP {status}')

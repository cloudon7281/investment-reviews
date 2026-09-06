#!/usr/bin/env python3
"""Create the next release tag and close the linked issue on PR merge.

The tag lineage is the one the repo declares in deploy/service.yaml (`tagScheme`, SDI §5.7);
SemVer is the default. SKIP_TAG=true skips tagging entirely (the documentation-repo workflow).
"""
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


def manifest_scalars(ref):
    """Top-level scalars from `deploy/service.yaml` at `ref`; {} when the repo has none.

    Deliberately not PyYAML: the jarvis Actions runner is host-mode and carries python3/curl/git and
    nothing else, which is the same reason gate-b.py hand-parses this file. SDI §5.7 declares its
    lineage as top-level scalars precisely so this parse is enough.
    """
    import base64
    status, obj = gitea('GET', f'contents/deploy/service.yaml?ref={ref}')
    if status != 200 or not isinstance(obj, dict) or not obj.get('content'):
        return {}
    raw = base64.b64decode(obj['content'].replace('\n', '')).decode('utf-8', 'replace')
    out = {}
    for line in raw.splitlines():
        if line[:1].isspace() or line.lstrip().startswith('#') or ':' not in line:
            continue
        key, _, value = line.partition(':')
        value = value.split('#', 1)[0].strip().strip('\'"')
        if value:
            out[key.strip()] = value
    return out


def all_tags():
    """Every tag name in the repo, paged.

    A single `?limit=50` page is a truncated view of the lineage, and a truncated view yields a
    wrong next tag rather than an error — `investment-reviews` already sits at exactly 50 tags.
    """
    names, page = [], 1
    while page <= 20:
        _, data = gitea('GET', f'tags?limit=50&page={page}')
        batch = data if isinstance(data, list) else []
        names += [t.get('name', '') for t in batch if t.get('name')]
        if len(batch) < 50:
            break
        page += 1
    return names



_, pr = gitea('GET', f'pulls/{PR_NUM}')

if not SKIP_TAG:
    # 0. Registration-freshness gate BEFORE tagging, so the deploy lands on a fresh registry
    #    (tier2-project#47). Ask registrard on EVERY tag-driven deploy, not just when this PR's
    #    diff touched deploy/service.yaml (tier2-project#127): registrard compares the current
    #    manifest digest against the one recorded at registration and applies devops-model#74
    #    §13.7 to the result, so a manifest change an earlier blocked PR left unregistered cannot
    #    slip out on the next unrelated merge. Register and deploy stay decoupled — this only
    #    sequences them. A gate failure withholds the tag (no broken deploy). Rollout-safe: only
    #    active where REGISTRARD_URL is configured; otherwise behaviour is unchanged.
    REGISTRARD_URL = os.environ.get('REGISTRARD_URL', '')
    REGISTRARD_SECRET = os.environ.get('REGISTRARD_SECRET', '')
    if REGISTRARD_URL:
        print('checking registration freshness via registrard before tagging')
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
            raise SystemExit(f'registrard freshness gate FAILED (HTTP {e.code}): {detail} -- not tagging; deploy blocked')
        except Exception as e:
            raise SystemExit(f'registrard call failed: {e} -- not tagging; deploy blocked')
    else:
        _, files = gitea('GET', f'pulls/{PR_NUM}/files')
        changed = [f.get('filename') for f in (files if isinstance(files, list) else [])]
        if 'deploy/service.yaml' in changed:
            print('NOTE: service.yaml changed but REGISTRARD_URL unset -- tagging anyway; '
                  'ensure the service was re-registered manually (tier2-project#47).')

    # 1. Determine version bump from the PR's labels OR the linked issue's labels.
    #    Historically only the PR's own labels were read, so a correctly-labelled
    #    `enhancement` *issue* whose PR was left unlabelled got a patch bump instead of
    #    a minor one (london-travel#14 shipped as v1.1.7, not v1.2.0). The issue is
    #    almost always the source of truth for enhancement-vs-fix, so inherit its labels
    #    via the PR's issue reference (closes/fixes/resolves/refs/references #N).
    #    Search the title as well as the body: `... (refs #N)` in the title is the house
    #    convention for a fix held open until it is verified, and body-only matching let
    #    exactly the same silent patch bump back in (tier2-project#148,
    #    tier4-guinea-pig#22 shipped as v1.2.3, not v1.3.0). Which reference decides the
    #    bump is logged, so a miss shows up in the Actions log rather than only in a
    #    surprising version number. NB the issue-close step below still reads the body
    #    alone — closing is a stronger action than bumping and Gitea's own keyword
    #    handling already covers the title.
    labels = [l['name'] for l in pr.get('labels', [])]
    ref = re.search(r'(?:closes|fixes|resolves|refs|references)\s+#(\d+)',
                    f"{pr.get('title') or ''}\n{pr.get('body') or ''}", re.IGNORECASE)
    if ref:
        _, ref_issue = gitea('GET', f'issues/{ref.group(1)}')
        inherited = [l['name'] for l in (ref_issue.get('labels') or [])]
        labels += inherited
        print(f'Inherited labels from linked issue #{ref.group(1)}: {inherited}')
    else:
        print('No linked issue reference in PR title or body — using the PR labels alone')
    print(f'Labels (PR + linked issue): {labels}')
    bump = 'minor' if 'enhancement' in labels else 'patch'
    print(f'Bump: {bump}')

    # 2. Compute the next tag in the lineage this repo declares (SDI §5.7).
    #    The declaration is read from the manifest at the commit being tagged, never from
    #    registration state: this runs in Actions, and a Tier-1 repo must be able to cut a tag while
    #    Tier-2 is down (deploy-model §5.1). Registration validates and publishes it; it is not on
    #    this path.
    _, branch = gitea('GET', 'branches/main')
    sha = branch['commit']['id']
    manifest = manifest_scalars(sha)
    scheme = manifest.get('tagScheme', 'semver')
    tags_list = all_tags()

    if scheme not in ('semver', 'upstream-build', 'none'):
        raise SystemExit(f'deploy/service.yaml: unknown tagScheme {scheme!r} '
                         f'(expected semver|upstream-build|none, SDI §5.7) -- not tagging')

    if scheme == 'none':
        next_tag = None
        print('tagScheme: none -- this repo is tagged by hand (SDI §5.7); no tag created')
    elif scheme == 'upstream-build':
        # <prefix>-<upstream>+<n>: the tag names the upstream release this wrapper approves. N
        # counts wrapper revisions WITHIN one upstream version, so it restarts at 1 when
        # upstreamVersion changes -- which falls out of matching only this version's tags.
        # The PR labels above decided a bump that does not apply here: there is no major/minor/patch
        # choice to make when the version in the tag is upstream's.
        prefix = manifest.get('tagPrefix', '')
        upstream = manifest.get('upstreamVersion', '')
        if not prefix or not upstream:
            raise SystemExit('deploy/service.yaml: tagScheme: upstream-build needs both tagPrefix '
                             'and upstreamVersion (SDI §5.7) -- not tagging')
        pat = re.compile(rf'^{re.escape(prefix)}-{re.escape(upstream)}\+(\d+)$')
        builds = [int(m.group(1)) for m in (pat.match(t) for t in tags_list) if m]
        print(f'Scheme: upstream-build, upstream {upstream}, existing builds: {sorted(builds)}')
        next_tag = f'{prefix}-{upstream}+{max(builds) + 1 if builds else 1}'
        print(f'Next: {next_tag}')
    else:
        semver = [t for t in tags_list if re.fullmatch(r'v\d+\.\d+\.\d+', t)]
        # Tags exist but none of them are SemVer, and nothing declared otherwise: this repo's
        # lineage is something the default cannot read, and starting a fresh one at v0.0.0 mints a
        # tag that looks installable and names nothing. That is how tier-1-gitea acquired fourteen
        # v0.x tags alongside its real gitea-<upstream>+<n> ones, one of which was installed as a
        # Tier-1 release (tier2-project#262). No tags AT ALL is still a genuine fresh start.
        if tags_list and not semver:
            raise SystemExit(
                f'{len(tags_list)} tag(s) exist and none are SemVer (newest: {tags_list[0]}) -- '
                f'refusing to start a new v0.0.x lineage. Declare this repo\'s lineage in '
                f'deploy/service.yaml (tagScheme, SDI §5.7) and re-run.')
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

    # 3. Create tag on the commit the manifest was read from (idempotent — 409 = already exists)
    if next_tag:
        status, _ = gitea('POST', 'tags',
                          {'tag_name': next_tag, 'target': sha, 'message': next_tag})
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

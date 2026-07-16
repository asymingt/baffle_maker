#!/usr/bin/env python3

import datetime
import html
import os
import sys
from urllib.parse import urlparse

from github import Github
from github import Auth

org_list = ['ros2', 'ament']
excluded_labels = ['backlog', 'help wanted', 'more-information-needed']
excluded_repos = ['ros2/safety_working_group', 'ros2/rmw_iceoryx', 'ros2/rosbag2', 'ros2/rclc', 'ros2/cartographer_ros', 'ros2/cartographer', 'ros2/domain_bridge', 'ros2/ros1_bridge']
excluded_projects = ['ros2/52']

# Bazel-logo-inspired greens, used throughout the generated site.
WAFFLE_DARK = '#12321f'
WAFFLE_DEEP = '#1b4d2e'
WAFFLE_BASE = '#2e7d32'
WAFFLE_MID = '#43a047'
WAFFLE_LIGHT = '#81c784'
WAFFLE_PALE = '#c8e6c9'
WAFFLE_MIST = '#e8f5e9'


def waffle_icon(size=48, cell_id='a'):
    """Return an inline SVG waffle icon (a green grid of waffle pockets)."""
    pad, cell, gap, cols = 10, 19, 8, 4
    cells = []
    for row in range(cols):
        for col in range(cols):
            x = pad + col * (cell + gap)
            y = pad + row * (cell + gap)
            cells.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="5" fill="url(#pocket-{cell_id})"/>')
    return f'''<svg class="waffle-icon" width="{size}" height="{size}" viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="waffle">
  <defs>
    <linearGradient id="body-{cell_id}" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{WAFFLE_MID}"/>
      <stop offset="100%" stop-color="{WAFFLE_BASE}"/>
    </linearGradient>
    <linearGradient id="pocket-{cell_id}" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{WAFFLE_DEEP}"/>
      <stop offset="100%" stop-color="{WAFFLE_DARK}"/>
    </linearGradient>
  </defs>
  <rect x="3" y="3" width="114" height="114" rx="20" fill="url(#body-{cell_id})" stroke="{WAFFLE_DARK}" stroke-width="3"/>
  {''.join(cells)}
</svg>'''


def waffle_favicon_data_uri():
    svg = waffle_icon(size=64, cell_id='fav').replace('\n', '')
    import base64
    encoded = base64.b64encode(svg.encode('utf-8')).decode('ascii')
    return f'data:image/svg+xml;base64,{encoded}'


def repo_from_url(url):
    parts = urlparse(url).path.strip('/').split('/')
    return '/'.join(parts[:2]) if len(parts) >= 2 else url


def build_search():
    today = datetime.date.today()
    start_delta = datetime.timedelta(days=14)
    start_day = today - start_delta
    updatestring = 'updated:>=%s' % start_day

    search_terms = []
    for org in org_list:
        search_terms.append('org:' + org)
    for xlabel in excluded_labels:
        search_terms.append('-label:"' + xlabel + '"')
    for xrepo in excluded_repos:
        search_terms.append('-repo:' + xrepo)
    for xproj in excluded_projects:
        search_terms.append('-project:' + xproj)
    search = ' '.join(search_terms) + ' state:open is:pr no:assignee -draft:true archived:false ' + updatestring
    return search


def fetch_rows(gh, search):
    rows = []
    for issue in gh.search_issues(search):
        if issue.pull_request is not None:
            url = issue.as_pull_request().html_url
            kind = 'PR'
        else:
            url = issue.html_url
            kind = 'Issue'
        rows.append({
            'repo': repo_from_url(url),
            'title': issue.title,
            'url': url,
            'kind': kind,
            'updated': issue.updated_at,
        })
    rows.sort(key=lambda r: (r['repo'], r['title']))
    return rows


def render_html(rows, search, generated_at):
    icon_lg = waffle_icon(size=64, cell_id='hero')
    icon_sm = waffle_icon(size=28, cell_id='row')
    favicon = waffle_favicon_data_uri()

    if rows:
        body_rows = []
        for row in rows:
            body_rows.append(f'''      <tr>
        <td class="col-icon">{icon_sm}</td>
        <td class="col-repo"><span class="pill">{html.escape(row['repo'])}</span></td>
        <td class="col-title"><a href="{html.escape(row['url'])}" target="_blank" rel="noopener">{html.escape(row['title'])}</a></td>
        <td class="col-kind">{html.escape(row['kind'])}</td>
        <td class="col-updated">{row['updated'].strftime('%b %d, %Y')}</td>
      </tr>''')
        table_html = f'''    <table>
      <thead>
        <tr>
          <th class="col-icon"></th>
          <th class="col-repo">Repository</th>
          <th class="col-title">Title</th>
          <th class="col-kind">Type</th>
          <th class="col-updated">Last updated</th>
        </tr>
      </thead>
      <tbody>
{chr(10).join(body_rows)}
      </tbody>
    </table>'''
    else:
        table_html = f'''    <div class="empty-plate">
      {icon_lg}
      <p>No waffles today &mdash; the plate is clean!</p>
    </div>'''

    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The Baffle Board</title>
<link rel="icon" href="{favicon}">
<style>
  :root {{
    --waffle-dark: {WAFFLE_DARK};
    --waffle-deep: {WAFFLE_DEEP};
    --waffle-base: {WAFFLE_BASE};
    --waffle-mid: {WAFFLE_MID};
    --waffle-light: {WAFFLE_LIGHT};
    --waffle-pale: {WAFFLE_PALE};
    --waffle-mist: {WAFFLE_MIST};
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background:
      radial-gradient(circle at 8px 8px, var(--waffle-pale) 2px, transparent 2px) 0 0 / 32px 32px,
      var(--waffle-mist);
    color: var(--waffle-dark);
    min-height: 100vh;
  }}
  .hero {{
    background: linear-gradient(135deg, var(--waffle-deep), var(--waffle-base) 55%, var(--waffle-mid));
    color: var(--waffle-mist);
    padding: 2.5rem 1.5rem 3rem;
    text-align: center;
    box-shadow: 0 6px 18px rgba(18, 50, 31, 0.35);
  }}
  .hero-icons {{
    display: flex;
    justify-content: center;
    gap: 0.75rem;
    margin-bottom: 1rem;
  }}
  .hero-icons .waffle-icon {{ filter: drop-shadow(0 3px 4px rgba(0,0,0,0.25)); }}
  .hero h1 {{
    margin: 0 0 0.35rem;
    font-size: 2.25rem;
    letter-spacing: 0.02em;
  }}
  .hero p {{
    margin: 0.25rem 0;
    opacity: 0.9;
  }}
  .badge {{
    display: inline-block;
    margin-top: 0.75rem;
    padding: 0.35rem 0.9rem;
    background: rgba(232, 245, 233, 0.15);
    border: 1px solid rgba(232, 245, 233, 0.4);
    border-radius: 999px;
    font-weight: 600;
    font-size: 0.9rem;
  }}
  main {{
    max-width: 1000px;
    margin: -1.75rem auto 3rem;
    padding: 0 1.5rem;
  }}
  .card {{
    background: white;
    border-radius: 16px;
    box-shadow: 0 10px 30px rgba(18, 50, 31, 0.18);
    overflow: hidden;
    border: 1px solid var(--waffle-pale);
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.95rem;
  }}
  thead th {{
    text-align: left;
    background: var(--waffle-mist);
    color: var(--waffle-deep);
    padding: 0.85rem 1rem;
    border-bottom: 2px solid var(--waffle-light);
    text-transform: uppercase;
    font-size: 0.75rem;
    letter-spacing: 0.06em;
  }}
  tbody tr {{
    border-bottom: 1px solid var(--waffle-mist);
    transition: background 0.15s ease;
  }}
  tbody tr:nth-child(even) {{ background: var(--waffle-mist); }}
  tbody tr:hover {{ background: var(--waffle-pale); }}
  td {{ padding: 0.65rem 1rem; vertical-align: middle; }}
  .col-icon {{ width: 44px; }}
  .pill {{
    display: inline-block;
    background: var(--waffle-pale);
    color: var(--waffle-deep);
    border-radius: 999px;
    padding: 0.2rem 0.7rem;
    font-size: 0.8rem;
    font-weight: 600;
    white-space: nowrap;
  }}
  .col-title a {{
    color: var(--waffle-base);
    text-decoration: none;
    font-weight: 600;
  }}
  .col-title a:hover {{ text-decoration: underline; }}
  .col-kind {{ color: var(--waffle-base); font-weight: 600; }}
  .col-updated {{ color: #5a6b5f; white-space: nowrap; }}
  .empty-plate {{
    text-align: center;
    padding: 3rem 1rem;
    color: var(--waffle-base);
  }}
  .empty-plate .waffle-icon {{ margin-bottom: 1rem; }}
  footer {{
    max-width: 1000px;
    margin: 0 auto 2rem;
    padding: 0 1.5rem;
    text-align: center;
    color: var(--waffle-base);
    font-size: 0.85rem;
  }}
  footer .waffle-icon {{ width: 20px; height: 20px; vertical-align: middle; margin: 0 2px; opacity: 0.7; }}
  code {{ background: var(--waffle-mist); padding: 0.1rem 0.4rem; border-radius: 4px; }}
  @media (max-width: 640px) {{
    table {{ font-size: 0.85rem; }}
    .col-updated, .col-kind {{ display: none; }}
  }}
</style>
</head>
<body>
  <div class="hero">
    <div class="hero-icons">{icon_lg}{icon_lg}{icon_lg}</div>
    <h1>The Baffle Board</h1>
    <p>Unassigned, unlabeled ROS&nbsp;2 &amp; ament pull requests waiting for a reviewer.</p>
    <span class="badge">{len(rows)} open on the plate</span>
  </div>
  <main>
    <div class="card">
{table_html}
    </div>
  </main>
  <footer>
    {icon_sm}{icon_sm}{icon_sm}
    <p>Generated {generated_at.strftime('%b %d, %Y %H:%M UTC')} by <code>baffle_maker</code>.</p>
  </footer>
</body>
</html>
'''


def write_site(html_content):
    workspace = os.environ.get('BUILD_WORKSPACE_DIRECTORY', os.getcwd())
    site_dir = os.path.join(workspace, 'site')
    os.makedirs(site_dir, exist_ok=True)
    out_path = os.path.join(site_dir, 'index.html')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print('Wrote %s' % out_path)


def main():
    key = os.environ.get('GITHUB_API_TOKEN')
    if not key:
        print("Error: GITHUB_API_TOKEN environment variable is not set.", file=sys.stderr)
        print("Please set it in your environment: export GITHUB_API_TOKEN=\"your_token\"", file=sys.stderr)
        return 1

    auth = Auth.Token(key)
    gh = Github(auth=auth)

    search = build_search()
    print("Search:", search)
    rows = fetch_rows(gh, search)
    for row in rows:
        print('%s,"%s"' % (row['url'], row['title']))

    html_content = render_html(rows, search, datetime.datetime.now(datetime.timezone.utc))
    write_site(html_content)

    return 0


if __name__ == '__main__':
    sys.exit(main())

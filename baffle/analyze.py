#!/usr/bin/env python3
# Copyright 2026 Open Source Robotics Foundation, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""CONTROLLER stage: reads the raw MODEL data file (query.py's output) and
classifies each contributor as Human, Unknown, Bot, or AI, writing the
result to a sibling "<date>_analyzed.yaml" file for the VIEW stage
(render.py) to consume.

Heuristic: community-engagement ratio = (public_issues + public_reviews) /
public_pull_requests. Genuine human contributors -- even prolific ones --
tend to review others' work and open issues at a rate roughly proportional
to how many PRs they open; automated/AI-driven PR farms mass-produce PRs
without that reciprocal engagement. Accounts with too few PRs to trust the
ratio are marked Unknown rather than guessed at. A literal "[bot]" suffix
(GitHub Apps, e.g. mergify[bot]) is always classified as Bot, separately
from the heuristic-driven AI bucket.

Accounts GitHub has hidden from its search API (query.py sets
"search_restricted") have no engagement numbers to work with, so they fall
back to a PR-burst heuristic: how many PRs the account has fired at the ROS
orgs, and how tightly clustered in time they are. Genuine contributors
don't open several PRs within minutes of each other.
"""

import datetime
import os
import re
import sys

import yaml

from common import ATTESTATION_CROSS
from common import ATTESTATION_TICK
from common import ATTESTATION_WARNING
from common import CLASSIFICATION_AI
from common import CLASSIFICATION_BOT
from common import CLASSIFICATION_HUMAN
from common import CLASSIFICATION_UNKNOWN
from common import find_latest_data_file

MIN_SAMPLE_PULL_REQUESTS = 10
LOW_ENGAGEMENT_THRESHOLD = 0.15
HIGH_ENGAGEMENT_THRESHOLD = 0.5

# Fallback heuristic for search-restricted accounts (see module docstring).
BURST_WINDOW_SECONDS = 3600
BURST_PR_THRESHOLD = 3            # >= this many PRs within one window -> AI
RESTRICTED_TOTAL_PR_THRESHOLD = 5  # >= this many concurrently-open PRs -> AI

# Matches the PR template's "### Did you use Generative AI?" heading and the
# "### Additional Information" heading that follows it, regardless of
# markdown decoration (#, *, etc.) around the words.
GENAI_QUESTION_RE = re.compile(r'did\s+you\s+use\s+generative\s+ai\??', re.IGNORECASE)
NEXT_SECTION_RE = re.compile(r'additional\s+information', re.IGNORECASE)
HTML_COMMENT_RE = re.compile(r'<!--.*?-->', re.DOTALL)
NON_LETTER_RE = re.compile(r'[^a-zA-Z]')


def engagement_ratio(stats):
    prs = max(stats.get('public_pull_requests', 0), 1)
    return (stats.get('public_issues', 0) + stats.get('public_reviews', 0)) / prs


def _max_events_in_window(sorted_epochs, window_seconds):
    """Largest number of timestamps falling within any window_seconds span."""
    start = 0
    best = 0
    for end in range(len(sorted_epochs)):
        while sorted_epochs[end] - sorted_epochs[start] > window_seconds:
            start += 1
        best = max(best, end - start + 1)
    return best


def pr_burst_by_author(rows):
    """Map author -> {'open_pr_count', 'max_burst'} from the visible (open,
    unassigned) PRs in the MODEL data. Only consulted for search-restricted
    accounts, where GitHub gives us no other history to go on."""
    epochs_by_author = {}
    for row in rows:
        if row.get('kind', 'PR') != 'PR':
            continue
        stamp = row.get('created') or row.get('updated')
        if not stamp:
            continue
        try:
            when = datetime.datetime.fromisoformat(stamp)
        except ValueError:
            continue
        epochs_by_author.setdefault(row['author'], []).append(when.timestamp())

    result = {}
    for author, epochs in epochs_by_author.items():
        epochs.sort()
        result[author] = {
            'open_pr_count': len(epochs),
            'max_burst': _max_events_in_window(epochs, BURST_WINDOW_SECONDS),
        }
    return result


def is_search_restricted(stats):
    # The explicit flag is set by current query.py runs; older cached
    # entries only show a null account_created_at with zeroed counts.
    return bool(stats.get('search_restricted')) or stats.get('account_created_at') is None


def classify_restricted_user(burst):
    if (burst.get('max_burst', 0) >= BURST_PR_THRESHOLD
            or burst.get('open_pr_count', 0) >= RESTRICTED_TOTAL_PR_THRESHOLD):
        return CLASSIFICATION_AI
    return CLASSIFICATION_UNKNOWN


def classify_user(username, stats, burst=None):
    if username.endswith('[bot]'):
        return CLASSIFICATION_BOT
    if is_search_restricted(stats):
        return classify_restricted_user(burst or {})
    if stats.get('public_pull_requests', 0) < MIN_SAMPLE_PULL_REQUESTS:
        return CLASSIFICATION_UNKNOWN
    ratio = engagement_ratio(stats)
    if ratio >= HIGH_ENGAGEMENT_THRESHOLD:
        return CLASSIFICATION_HUMAN
    # A ratio of exactly zero is as consistent with "human who has simply
    # never opened an issue or left a review" as with a PR farm, so it
    # isn't strong enough evidence on its own to call AI.
    if 0 < ratio < LOW_ENGAGEMENT_THRESHOLD:
        return CLASSIFICATION_AI
    return CLASSIFICATION_UNKNOWN


def classify_ai_attestation(body):
    """Classify a PR body's answer to the template's "Did you use Generative
    AI?" question. Missing question or blank/comment-only answer -> warning;
    an answer of exactly "No" -> cross; any other answer -> tick."""
    if not body:
        return ATTESTATION_WARNING
    question_match = GENAI_QUESTION_RE.search(body)
    if not question_match:
        return ATTESTATION_WARNING

    section_match = NEXT_SECTION_RE.search(body, question_match.end())
    section_end = section_match.start() if section_match else len(body)
    answer = HTML_COMMENT_RE.sub('', body[question_match.end():section_end]).strip()

    # Discard pure markdown noise (leftover heading markers, list bullets,
    # etc.) -- e.g. a bare "###" before the next section heading, once HTML
    # comments are stripped out, doesn't count as a real answer.
    if not NON_LETTER_RE.sub('', answer):
        return ATTESTATION_WARNING

    first_line = next((line.strip() for line in answer.splitlines() if line.strip()), '')
    if NON_LETTER_RE.sub('', first_line).lower() == 'no':
        return ATTESTATION_CROSS
    return ATTESTATION_TICK


def analyzed_file_path(data_path):
    stem, ext = os.path.splitext(os.path.basename(data_path))
    return os.path.join(os.path.dirname(data_path), '%s_analyzed%s' % (stem, ext))


def main():
    workspace = os.environ.get('BUILD_WORKSPACE_DIRECTORY', os.getcwd())
    site_dir = os.path.join(workspace, 'site')

    data_path = sys.argv[1] if len(sys.argv) > 1 else find_latest_data_file(site_dir)
    if not data_path:
        print("Error: no dated YAML file found in %s. Run the query tool first." % site_dir, file=sys.stderr)
        return 1

    with open(data_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    rows = data.get('pull_requests', [])
    users = data.get('users', {})
    burst_by_author = pr_burst_by_author(rows)
    for username, stats in users.items():
        burst = burst_by_author.get(username, {})
        stats['classification'] = classify_user(username, stats, burst)
        if is_search_restricted(stats):
            # Record what drove the call for an otherwise data-free account.
            stats['open_pr_count'] = burst.get('open_pr_count', 0)
            stats['max_pr_burst'] = burst.get('max_burst', 0)

    for row in rows:
        row['ai_attestation'] = classify_ai_attestation(row.get('body', ''))

    out_path = analyzed_file_path(data_path)
    with open(out_path, 'w', encoding='utf-8') as f:
        yaml.safe_dump(data, f, sort_keys=False)
    print('Wrote %s' % out_path)

    return 0


if __name__ == '__main__':
    sys.exit(main())

#!/bin/bash
#
# Cut a new firmware release. Mirrors ncSender's .scripts/release.sh:
#   - auto-bump the version (patch++, rollover to next minor at 1000)
#   - generate user-facing release notes from the commit log (via the `claude` CLI,
#     with a basic-categorization fallback)
#   - create an annotated tag carrying those notes, and push it
#
# Pushing the tag triggers .github/workflows/build.yml, which builds the firmware
# .bin + .hex and publishes the GitHub Release using the tag's notes.
#
# Usage:  ./scripts/release.sh     (run from a clean main/release branch)

set -e

# Latest stable tag (vMAJOR.MINOR.PATCH, excluding -beta); else start fresh.
LATEST_TAG=$(git tag --sort=-version:refname | grep -E '^v[0-9]+\.' | grep -v '\-beta' | head -1)
HAS_TAG=true
if [ -z "$LATEST_TAG" ]; then
    HAS_TAG=false
    LATEST_TAG="v0.1.0"     # the very first release uses this as-is
fi
echo "Latest tag: $LATEST_TAG"

# Base version (strip 'v' and any -prerelease suffix)
VERSION=${LATEST_TAG#v}
VERSION=${VERSION%%-*}
IFS='.' read -r MAJOR MINOR PATCH <<< "$VERSION"

# First release uses the base as-is; afterwards bump the patch (rollover at 1000).
if [ "$HAS_TAG" = true ]; then
    PATCH=$((PATCH + 1))
    if [ "$PATCH" -ge 1000 ]; then
        MINOR=$((MINOR + 1))
        PATCH=0
    fi
fi
NEW_VERSION="$MAJOR.$MINOR.$PATCH"
NEW_TAG="v$NEW_VERSION"
echo "New version: $NEW_VERSION"
echo "New tag: $NEW_TAG"

# Working tree must be clean
if [ -n "$(git status --porcelain)" ]; then
    echo "Working tree is not clean. Commit or stash changes first."
    exit 1
fi

# Must have new commits since the last tag
echo ""
if [ "$HAS_TAG" = true ]; then
    COMMIT_COUNT=$(git rev-list "$LATEST_TAG..HEAD" --count)
    COMMITS=$(git log "$LATEST_TAG..HEAD" --pretty=format:"%s")
else
    COMMIT_COUNT=$(git rev-list HEAD --count)
    COMMITS=$(git log --pretty=format:"%s")
fi
if [ "$COMMIT_COUNT" = "0" ]; then
    echo "No new commits since $LATEST_TAG. Nothing to release."
    exit 1
fi
echo "$COMMIT_COUNT commit(s) since $LATEST_TAG"

echo ""
echo "Generating release notes using Claude..."
echo ""

PROMPT="Generate release notes for version $NEW_VERSION from ONLY the following commit messages. Do NOT invent, assume, or add any changes not explicitly listed below.

Commit messages:
$COMMITS

CRITICAL: Output ONLY the exact markdown format shown below. Do NOT add ANY other text.

Required format:
## What's Changed

### [emoji] [Category Name]
- [change description]

Rules:
1. Start with exactly \"## What's Changed\"
2. Group by category with emojis (e.g. :rocket: New Features, :bug: Bug Fixes, :wrench: Improvements)
3. Write from the USER's perspective - describe what they can now do or what was fixed for them, not internal code details
4. SKIP commits that are purely internal (test updates, refactors, CI fixes, code cleanup) - users do not care about these
5. If multiple commits relate to the same user-facing change, combine them into a single bullet point
6. Do NOT fabricate changes that are not in the commit list
7. No markdown code blocks, URLs, links, or non-English characters
8. If after filtering out internal commits there are no user-facing changes, output: \"## What's Changed\n\n- Internal improvements and maintenance\"

Output ONLY the markdown. No preamble. No explanation. Just the markdown."

RELEASE_NOTES=$(claude -p --system-prompt "You are a release note generator for grblHAL firmware for the Onefinity RTS-1 CNC controller. Write notes for end users (machine owners), not developers. Only use the commit messages provided. Never invent changes. Skip internal-only changes like test fixes, refactors, and CI updates." "$PROMPT" 2>&1)
CLAUDE_EXIT_CODE=$?

if [ $CLAUDE_EXIT_CODE -ne 0 ] || [ -z "$RELEASE_NOTES" ]; then
    echo "Failed to generate release notes with Claude (is the 'claude' CLI installed?)."
    echo "Falling back to basic categorization..."

    RELEASE_NOTES="## What's Changed"$'\n'
    FEATURES=$(echo "$COMMITS" | grep -i "^feat\|^feature\|^add" || true)
    FIXES=$(echo "$COMMITS" | grep -i "^fix\|^bug" || true)
    OTHER=$(echo "$COMMITS" | grep -iv "^feat\|^feature\|^add\|^fix\|^bug\|^chore" || true)

    if [ -n "$FEATURES" ]; then
        RELEASE_NOTES+=$'\n'"### New Features"$'\n'
        while IFS= read -r line; do
            CLEAN_LINE=$(echo "$line" | sed -E 's/^(feat|feature|add|Add|Feature|Feat)://i' | sed 's/^[[:space:]]*//')
            RELEASE_NOTES+="- $CLEAN_LINE"$'\n'
        done <<< "$FEATURES"
    fi
    if [ -n "$FIXES" ]; then
        RELEASE_NOTES+=$'\n'"### Bug Fixes"$'\n'
        while IFS= read -r line; do
            CLEAN_LINE=$(echo "$line" | sed -E 's/^(fix|bug|Fix|Bug)://i' | sed 's/^[[:space:]]*//')
            RELEASE_NOTES+="- $CLEAN_LINE"$'\n'
        done <<< "$FIXES"
    fi
    if [ -n "$OTHER" ]; then
        RELEASE_NOTES+=$'\n'"### Other Changes"$'\n'
        while IFS= read -r line; do
            RELEASE_NOTES+="- $line"$'\n'
        done <<< "$OTHER"
    fi
else
    echo "Release notes generated successfully"
fi

echo ""
echo "========================================="
echo "Release Notes for $NEW_TAG:"
echo "========================================="
echo "$RELEASE_NOTES"
echo "========================================="
echo ""

# Annotated tag on HEAD carrying the notes; the workflow reads them back.
git tag -a "$NEW_TAG" --cleanup=verbatim -m "$RELEASE_NOTES"
git push origin "$NEW_TAG"

echo ""
echo "Successfully created and pushed $NEW_TAG"
echo "CI will build the release at: https://github.com/siganberg/grblHal.rts-1/actions"

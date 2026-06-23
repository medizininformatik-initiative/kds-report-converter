# Development


## Release Checklist

1. Create a new release branch release/v<version> from main
2. Update the CHANGELOG based on commit history
3. Create a commit with the title `Release v<version>`
4. Create a PR from the release branch into the main branch
5. Merge that PR (after proper review)
6. Create and push a tag called `v<version>` like `v1.1.0` on the main branch at the merge commit
7. Create release notes on GitHub

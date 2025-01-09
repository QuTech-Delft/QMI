# Release procedure

This is the release procedure of a minor release for QMI. Major release procedure TBD.

The `<major>`, `<minor>` and `<patch>` refer to the versioning numbers of the current release to be made.

If you are using e.g. Git Bash on Windows, the `bump2version` command probably needs also extension: `bump2version.exe`.

## Steps

1. Create a new branch name `stable-<major>-<minor>` and check it out locally.
    ```shell script
    git checkout -b stable-{major}-{minor}
    ```
2. Replace in `CHANGELOG.md` the `## \[x.y.z] - Unreleased` line with `## [<major>.<minor>.<patch>] - <yyyy>-<mm>-<dd>` line.
3. Commit the CHANGELOG.md change:
    ```shell script
    git add CHANGELOG.md
    git commit -m "Update the CHANGELOG.md release header"
    ```
4. Run `bump2version` to increment to release version and to create a tag:
    ```shell script
    bump2version release --commit --tag --tag_name v<major>.<minor>.<patch>
    ```
5. Push these files and see that the pipelines pass.
    ```shell script
    git push --set-upstream origin stable-<major>-<minor>
    ```
6. Push the tag:
    ```shell script
    git push origin v{major}.{minor}.{patch}
    ```
7. Find the tag in the GitHub page, and make a release with as comments the latest `CHANGELOG.md` notes.
8. See that the tag has created the package and uploaded it into Pypi.
9. Revert the badges to point back to `main` branch:
    ```shell script
    bump2version minor --config-file .bumpreadme_rel.cfg --allow-dirty
    ```
10. Git add, commit and push to branch:
    ```shell script
    git add README.md
    git commit -m "Update README.md"
    git push origin
    ```
11. Checkout `main` branch:
    ```shell script
    git checkout main
    ```
12. Obtain the CHANGELOG.md from the stable branch:
    ```shell script
    git checkout stable-{major}-{minor} -- CHANGELOG.md
    ```
13. Add `## \[x.y.z] - Unreleased` line back into the `CHANGELOG.md` file.
14. Checkout a new branch named `stable-to-main` and check it out locally:
    ```shell script
    git checkout -b stable-to-main
    ```
15. Bump the version to next beta version with:
    ```shell script
    bump2version minor --commit
    ```
16. Update the `README.md` to point back to `main` branch for badges:
    ```shell script
    bump2version minor --config-file .bumpreadme_min.cfg --allow-dirty
    ```
17. Amend the CHANGELOG.md and README.md to the previous minor bump commit:
    ```shell script
    git add CHANGELOG.md README.md
    git commit --amend
    ```
18. Push these files and see that the pipelines pass:
    ```shell script
    git push
    ```
19. After the pipeline has passed, in the GitHub page create a pull request for this new branch with `main` as target.
20. Get the PR approved and then merge to `main`.

## Patch release

The following steps assume that the patch to be applied is in a single upstream commit (either in feature branch or on
the `main` branch) and that the `CHANGELOG.md` has been updated in that commit.
1. Checkout the stable branch that you want to patch:
    ```shell script
    git checkout stable-{major}-{minor}
    ```
2. Increase the patch number:
    ```shell script
    bump2version patch --commit
    ```
3. Cherry-pick the patch into the stable branch:
    ```shell script
    git cherry-pick -x {commit-hash}
    ```
4. Clean up the `CHANGELOG.md`, removing references to changes that were not in the history of this stable branch.
5. Git add the changed `CHANGELOG.md`:
    ```shell script
    git add CHANGELOG.md
    ```
6.  Increment the release:
    ```shell script
    bump2version release --commit --tag --tag_name v<major>.<minor>.<patch+1>
    ```
7.  Push everything:
    ```shell script
    git push origin
    git push origin v{major}.{minor}.{patch+1}
    ```
8.  Find the tag in the GitHub page, and make a release with as comments the latest `CHANGELOG.md` notes.
9.  See that the tag has created the package and uploaded it into Pypi.
10. Revert the badges to point back to `main` branch:
    ```shell script
    bump2version minor --config-file .bumpreadme_rel.cfg --allow-dirty
    ```
11. Git add, commit and push to branch:
    ```shell script
    git add README.md
    git commit -m "Update README.md"
    git push origin
    ```

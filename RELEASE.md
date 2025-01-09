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
9. Update also the `README.md` to point back to 'main' branch for badges
    ```shell script
    bump2version minor --config-file .bumpreadme_rel.cfg --allow-dirty
    ```
10. Bump the version to new minor version with
    ```shell script
    bump2version minor --commit
    ```
11. Update also the `README.md` to point back to 'main' branch for badges
    ```shell script
    bump2version minor --config-file .bumpreadme_min.cfg --allow-dirty
    ```
12. Add `## \[x.y.z] - Unreleased` line back into the `CHANGELOG.md` file.
13. Amend the CHANGELOG.md and README.md to the previous minor bump commit:
    ```shell script
    git add CHANGELOG.md README.md
    git commit --amend
    ```
14. Push these files and see that the pipelines pass.
    ```shell script
    git push
    ```
15. After the pipeline has passed, in the GitHub page create a pull request for this new branch with `main` as target.
16. Get the PR approved and then merge to `main`.

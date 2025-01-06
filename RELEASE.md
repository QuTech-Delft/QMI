# Release procedure

This is the release procedure of a minor release for QMI. Major release procedure TBD.

The `<major>`, `<minor>` and `<patch>` refer to the versioning numbers of the current release to be made.

## Steps

1. Create a new branch name `stable-<major>-<minor>` and check it out locally.
```shell script
git checkout -b stable-{major}-{minor}
```
2. Run `bump2version` to increment the release:
```shell script
bump2version release --commit
```
3. Run `bump2version` to increment the `README.md` to have the latest release number:
```shell script
bump2version.exe minor --config-file .bumpreadme_min.cfg --allow-dirty
```
4. Replace in `CHANGELOG.md` the `## \[x.y.z] - Unreleased` line with `## [<major>.<minor>.<patch>] - <yyyy>-<mm>-<dd>` line.
5. Amend the CHANGELOG.md and README.md to the previous release bump commit:
```shell script
git add CHANGELOG.md README.md
git commit --amend
```
6. Push these files and see that the pipelines pass.
```shell script
git push --set-upstream origin stable-0-46
```
7. Tag the release:
```shell script
git tag v{major}.{minor}.{patch}
```
8. Push the tag:
```shell script
git push origin v{major}.{minor}.{patch}
```
9. Find the tag in the Github page, and make a release with as comments the latest `CHANGELOG.md` notes.
10. See that the tag has created the package and uploaded it into Pypi.
11. Create a new branch `stable-to-main`
```shell script
git checkout -b stable-to-main
```
12. Bump the version to new minor version with
```shell script
bump2version minor --commit
```
13. Update also the `README.md` to point back to 'main' branch for badges
```shell script
bump2version.exe release --config-file .bumpreadme_min.cfg --allow-dirty
```
14. Add `## \[x.y.z] - Unreleased` line back into the `CHANGELOG.md` file.
15. Amend the CHANGELOG.md and README.md to the previous minor bump commit:
```shell script
git add CHANGELOG.md README.md
git commit --amend
```
16. Push these files and see that the pipelines pass.
```shell script
git push --set-upstream origin stable-to-main
```
17. After the pipelines have passed, in the Github page create a pull request for this new branch with `main` as target.
18. Get the PR approved and then merge to `main`.

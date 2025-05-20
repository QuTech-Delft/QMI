# Release procedure

This is the release procedure of a minor release for QMI. Major release procedure TBD.

The `<major>`, `<minor>` and `<patch>` refer to the versioning numbers of the current release to be made.

If you are using e.g. Git Bash on Windows, the `bump2version` command probably needs also extension: `bump2version.exe`.

## Steps

1. Create a new branch name `stable-<major>-<minor>` and check it out locally.
    ```shell script
    git checkout -b stable-{major}-{minor}
    ```
2. Run `bump2version` to update the files which contain references to `main` to the new stable branch.
    ```shell script
    bump2version release --config-file=.bumpversion_switch.cfg --commit
    ```
3. Run `bump2version` to create a release version and a tag:
    ```shell script
    bump2version release --config-file=.bumpversion_release.cfg --commit --tag
    ```
4. Push the branch to origin and see that it passes the workflow.
    ```shell script
    git push --set-upstream origin stable-<major>-<minor>
    ```
5. Push the tag to origin:
    ```shell script
    git push origin v{major}.{minor}.{patch} 
    ```
6. If the tag passes the workflow, do the following:
  - Find the tag in GitHub and make a release with the latest `CHANGELOG.md` entry.
  - See that the release has set as the latest package and that a new release has been uploaded to Pypi.
7. Checkout `main` branch:
    ```shell script
    git checkout main
    ```
8. Checkout a new branch named `bump-minor-on-main` and check it out locally:
    ```shell script
    git checkout -b bump-minor-on-main
    ```
9. Obtain the CHANGELOG.md from the tagged release:
    ```shell script
    git checkout v{major}.{minor}.{patch} -- CHANGELOG.md
    ```
10. Add `## [VERSION] - Unreleased` at the top of the `CHANGELOG.md` to prepare it for the new beta minor version and stage it.
    ```shell script
    git add CHANGELOG.md
    ```
11. Run `bump2version` to create the beta minor version on main:
    ```shell script
    bump2version minor --config-file=.bumpversion_main.cfg --allow-dirty --commit
    ```
12. Push the branch to origin:
    ```shell script
    git push origin bump-minor-on-main
    ```
13. If the branch passes the workflow, do the following:
  - Create a pull request for this new branch with `main` as target.
  - Get the PR approved and then merge to `main`.

## Patch release

The following steps assume that the patch to be applied is in a single upstream commit (either in feature branch or on
the `main` branch) and that the `CHANGELOG.md` has been updated in that commit.
``NOTE: if the patch involves any of the files containing version of the release, the cherry-pick might cause issues and 
need another commit to fix the version numbering, or file-specific checkouts from main might have to be done, again with manual edits.``
1. Checkout the stable branch that you want to patch:
    ```shell script
    git checkout stable-{major}-{minor}
    ```
2. Add `## [VERSION] - Unreleased` at the top of the `CHANGELOG.md` to prepare it for the new beta patch version and stage it.
    ```shell script
    git add CHANGELOG.md
    ```
3. Run `bump2version` to create the beta patch version on stable:
    ```shell script
    bump2version patch --config-file=.bumpversion_stable.cfg --allow-dirty --commit
    ```
4. Cherry-pick the patch into the stable branch:
    ```shell script
    git cherry-pick -x {commit-hash}
    ```
5. Restore the `CHANGELOG.md` and update it with the relevant change/fix, and stage it.
    ```shell script
    git restore CHANGELOG.md
    git add CHANGELOG.md
    ```
6. Run `bump2version` to create a release version and a tag:
    ```shell script
    bump2version release --config-file=.bumpversion_release.cfg  --allow-dirty --commit --tag
    ```
7. Push the branch and tag to origin:
    ```shell script
    git push origin stable-{major}-{minor} v{major}.{minor}.{patch} 
    ```
8. If the tag passes the workflow, do the following:
  - Find the tag in GitHub and make a release with the latest `CHANGELOG.md` entry.
  - See that the release has created a package and upload it to Pypi.
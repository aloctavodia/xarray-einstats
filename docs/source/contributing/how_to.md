# Contributing How-to Guides

## Making a new release

1. Create a new branch
1. Review the change log (`docs/source/changelog.md`)
1. Update the version number, that is, remove the `dev` flag, it should not
   be increased.
1. Rerun the notebooks in `docs/source/tutorials`
1. Open a PR, make sure docs build correctly and all tests pass.
   Once everything is green, merge the PR
1. Create a new release from GitHub, use as tag the version number prepended
   by `v`. i.e. `v0.1.0` or `v0.2.3`
1. Check the new version appears on the readthedocs version switcher. If it doesn't
   go to [readthedocs](https://readthedocs.org/projects/xarray-einstats/) and
   add it.
1. Bump the minor version, set the patch version to 0 and add the `dev` flag

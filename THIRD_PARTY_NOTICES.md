# Third-party notices

FreshCtx core has no required third-party runtime dependency.

The optional `freshctx[postgres]` extra installs Psycopg and its binary distribution. Psycopg is a separate project distributed under the GNU Lesser General Public License version 3, with its own notices and source-availability terms. Installing or redistributing that optional dependency requires reviewing the exact Psycopg package artifacts and license files used in the release environment.

Development and test dependencies are not part of the FreshCtx runtime wheel. Their licenses are recorded in the private release-candidate license audit and must be rechecked for the exact tagged release build.

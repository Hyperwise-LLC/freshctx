from freshctx import FreshnessStatus

# The HTTP adapter performs conditional revalidation. A changed ETag or body
# produces STALE_SOURCE; a timeout or network failure produces UNVERIFIABLE.
print(FreshnessStatus.STALE_SOURCE.value)

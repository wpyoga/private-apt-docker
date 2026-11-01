#include <git2.h>
#include <stdio.h>

int main(void)
{
    int major, minor, patch;
    git_repository *repository = NULL;

    if (git_libgit2_init() < 0)
        return 1;

    git_libgit2_version(&major, &minor, &patch);
    printf("libgit2 %d.%d.%d\n", major, minor, patch);
    if (major != 1 || minor != 9)
        return 2;

    if (git_repository_init(&repository, "/tmp/libgit2-smoke", 1) < 0)
        return 3;

    git_repository_free(repository);
    git_libgit2_shutdown();
    return 0;
}

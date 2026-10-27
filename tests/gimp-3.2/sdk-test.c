#include <libgimp/gimp.h>
#include <libgimp/gimpui.h>
#include <stdio.h>

int main(void)
{
    int major, minor, micro;
    GimpParasite *parasite = gimp_parasite_new("sdk-test", 0, 0, NULL);
    gimp_parasite_free(parasite);

    gegl_get_version(&major, &minor, &micro);
    if (major != 0 || minor != 4 || micro < 66) {
        fprintf(stderr, "SDK linked an older system GEGL: %d.%d.%d\n", major, minor, micro);
        return 1;
    }

    babl_get_version(&major, &minor, &micro);
    if (major != 0 || minor != 1 || micro < 116) {
        fprintf(stderr, "SDK linked an older system Babl: %d.%d.%d\n", major, minor, micro);
        return 1;
    }

    puts("SDK_COMPILE_LINK_PASS: private GEGL/Babl with distro development packages installed");
    return 0;
}

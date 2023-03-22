#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

// stolen from https://access.redhat.com/articles/65410
static int pm_qos_fd = -1;

void start_low_latency(void) {
    int32_t target = 0;

    if (pm_qos_fd >= 0)
        return;

    pm_qos_fd = open("/dev/cpu_dma_latency", O_RDWR);
    if (pm_qos_fd < 0) {
        fprintf(stderr, "Failed to open PM QOS file: %s\n", strerror(errno));
        exit(errno);
    }
    write(pm_qos_fd, &target, sizeof(target));
}

void stop_low_latency(void) {
    if (pm_qos_fd >= 0)
        close(pm_qos_fd);
}

int main() {
    start_low_latency();
    printf("Press [enter] to restore\n");
    getchar();
    stop_low_latency();
    return 0;
}

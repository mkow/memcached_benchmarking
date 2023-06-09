#!/usr/bin/env python3

import socket
import subprocess
import sys
import time
import tqdm
from random import randint

HOST = '127.0.0.1'
PORT = 10000 + randint(0, 20000)
COMMITS = [
    ('origin', '634d0392c3acec724dad5a6af8e6305f166eca57', 'master'), # merge_base(master, borys/handle_map)
    ('origin', '46c5b157012dce9c7cf943fc7fe9e4e27a20eeaf', 'rwlock'), # borys/handle_map
]

def spawn_server(srv_binary, prepended_args, threads):
    # -t, --threads=<num>       number of threads to use (default: 4)
    # -c, --conn-limit=<num>    max simultaneous connections (default: 1024)
    # -p, --port=<num>          TCP port to listen on (default: 11211)
    # -B, --protocol=<name>     protocol - one of ascii, binary, or auto (default: auto-negotiate)
    p = subprocess.Popen(executable=srv_binary, args=[srv_binary] + prepended_args + [
        '-t', str(threads),
        '-c', '4096',
        '-p', str(PORT),
        '-B', 'binary',
    ])
    wait_for_server(HOST, PORT)
    return p

def wait_for_server(host, port):
    print('Waiting for the server...')
    while True:
        try:
            with socket.create_connection((HOST, PORT)) as s:
                break
        except ConnectionRefusedError:
            time.sleep(0.1)
    print('Server is up!')

def kill_server(p):
    print('Killing server...')
    p.terminate()
    p.wait()
    print('Done.')

def cut_between(source, before, after):
    pos1 = source.find(before)
    pos2 = source.find(after, pos1 + len(before))
    assert pos1 != -1
    assert pos2 != -1
    return source[pos1 + len(before) : pos2]

def benchmark(req_size, time_s):
    # --distinct-client-seed     Use a different random seed for each client
    # --key-maximum=NUMBER       Key ID maximum value (default: 10000000)
    # -d  --data-size=SIZE       Object data size in bytes (default: 32)
    # --randomize                random seed based on timestamp (default is constant value)
    # --test-time=SECS           Number of seconds to run the test
    # --ratio=RATIO              Set:Get ratio (default: 1:10)
    # --pipeline=NUMBER          Number of concurrent pipelined requests (default: 6)
    # -c, --clients=NUMBER           Number of clients per thread (default: 50)
    # -t, --threads=NUMBER           Number of threads (default: 4)
    p = subprocess.run([
        './memtier_benchmark/memtier_benchmark',
        '-s', HOST,
        '-p', str(PORT),
        '--protocol=memcache_binary',
        '--hide-histogram',
        '--distinct-client-seed',
        '--key-maximum=100000',
        f'-d {req_size}',
        '--randomize',
        f'--test-time={time_s}',
        '--ratio=1:9',
        '--pipeline=6',
        '-c', '6',
        '-t', '7',
    ], capture_output=True)
    output = p.stdout.decode()
    # [Ops/sec, Hits/sec, Misses/sec, Avg. Latency, p50 Latency, p99 Latency, p99.9 Latency, KB/sec]
    stats_gets = [float(x) for x in cut_between(output, '\nGets', '\n').split()]
    stats_total = [float(x) for x in cut_between(output, '\nTotals', '\n').split()]
    # fix up hits and misses to be percentage and thus make them actually useful
    stats_total[1] = stats_total[1] / stats_gets[0]
    stats_total[2] = stats_total[2] / stats_gets[0]
    return stats_total

def test_config(srv_binary, prepended_args, srv_threads=16, req_size=4096):
    srv = spawn_server(srv_binary, prepended_args, srv_threads)
    res = benchmark(req_size, time_s=30)
    # res = benchmark(req_size, time_s=180)
    kill_server(srv)
    return res

def test_native():
    return test_config('./memcached', [])

def test_direct():
    return test_config('gramine-direct', ['./memcached'])

def test_sgx():
    return test_config('gramine-sgx', ['./memcached'])

def print_stats(stats):
    fmt = '{:<14}' + '{:>15}' * 8
    print(fmt.format(' ', 'Ops/s', 'Hits', 'Misses', 'Avg. Latency', 'p50 Latency', 'p99 Latency', 'p99.9 Latency', 'KB/s'))
    for name, nums in stats:
        nums = nums[:]
        nums[0] = f'{nums[0]*100:.1f}%'
        nums[1] = f'{nums[1]*100:.1f}%'
        nums[2] = f'{nums[2]*100:.1f}%'
        print(fmt.format(name, *nums))

def print_delta_stats(stats, baseline, include_only=None):
    if include_only is None:
        include_only = [key for key, _ in stats if key != baseline]
    include_only = set(include_only)
    fmt = '{:<14}' + '{:>15}' * 8
    print(fmt.format('⊥'+baseline, 'Ops/s', 'Hits', 'Misses', 'Avg. Latency', 'p50 Latency', 'p99 Latency', 'p99.9 Latency', 'KB/s'))
    for name, nums in stats:
        if name == baseline:
            baseline_stats = nums
            break
    else:
        raise RuntimeError('unknown baseline')
    for name, nums in stats:
        if name not in include_only:
            continue
        nums = [f'{(num-base)/base*100:+.1f}%' for base, num in zip(baseline_stats, nums)]
        print(fmt.format('Δ' + name, *nums))

def main_rwlock_benchmark(args):
    if len(args) < 1:
        print(f'Usage: {args[0]} CHECKOUT_COMMAND_TEMPLATE')
        return 2
    results = []

    subprocess.run('make -j8', shell=True, check=True)
    print('Running native...')
    native_stats = test_native()
    results.append(('native', native_stats))

    for remote, commit, title in COMMITS:
        # the ugly part
        print(f'Checking {remote}/{commit}...')
        assert 'REMOTE' in args[1]
        assert 'COMMIT' in args[1]
        subprocess.run(args[1].replace('REMOTE', remote).replace('COMMIT', commit), shell=True, check=True)
        subprocess.run('make clean && make -j8 SGX=1', shell=True, check=True)
        print('Running direct...')
        direct_stats = test_direct()
        results.append((title + '-direct', direct_stats))
        print('Running sgx...')
        sgx_stats = test_sgx()
        results.append((title + '-sgx', sgx_stats))

    print_stats(results)
    print()
    print_delta_stats(
        stats = results,
        baseline = 'native',
    )
    print()
    print_delta_stats(
        stats = results,
        baseline = 'master-direct',
        include_only = ['rwlock-direct']
    )
    print()
    print_delta_stats(
        stats = results,
        baseline = 'master-sgx',
        include_only = ['rwlock-sgx']
    )
    return 0

if __name__ == '__main__':
    raise SystemExit(main_rwlock_benchmark(sys.argv))

#!/usr/bin/env python3

#
# Copyright 2023 Signal Messenger, LLC
# SPDX-License-Identifier: AGPL-3.0-only
#

import argparse
import hashlib
import os
import platform
import sys
import tarfile
import urllib.request

from typing import BinaryIO

UNVERIFIED_DOWNLOAD_NAME = "unverified.tmp"

PREBUILD_CHECKSUMS = {
    'android': 'e9fae8e1dcbb837bba669c3aa22f7f61ab0cefbc4b0f70a44aaf2a76f7e2a464',
    'ios': '74f94b1a5c974c1dffe38304c339ef587dc32245db69c4d8184282afcf8d6e71',
    'windows-x64': 'e30da35e168b377557f5234ab0ad62da440cfad338e30fd636d869c60b87ff58',
    'windows-arm64': 'ec3d6198b455edf8ea93de7e734115928add6ea96f77a38ee62dc2b53b53c18e',
    'mac-x64': '3ea7cb23bc0e0258a3f1142004a597d0ae4e5712084008d682941ea689ebb92a',
    'mac-arm64': '3f091086565a54764428c818935f0c020ac3b54437c77cfe002602a7a9bc2a35',
    'linux-x64': '18365c39ce9542bc0b62feaeffbad367349d6b7d93d089c5792bad072c2c5bce',
    'linux-arm64': '091ee72acba704e39d162093601b453d0f22b074944a83e4c810a893a25e64d0',
}


def resolve_platform(platform_name: str) -> str:
    if platform_name in PREBUILD_CHECKSUMS:
        return platform_name

    if platform_name in ['windows', 'mac', 'linux']:
        arch_name = platform.machine().lower()
        if arch_name in ['x86_64', 'amd64']:
            return resolve_platform(platform_name + '-x64')
        if arch_name in ['arm64', 'aarch64']:
            return resolve_platform(platform_name + '-arm64')
        raise AssertionError('unsupported architecture: ' + arch_name)

    if platform_name == 'desktop':
        os_name = platform.system().lower()
        if os_name == 'darwin':
            return resolve_platform('mac')
        return resolve_platform(os_name)

    raise AssertionError('unsupported platform: ' + platform_name)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Download and unpack a build artifact archive for a given platform, or from an arbitrary URL.')
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument('-u', '--url',
                              help='URL of an explicitly-specified artifact archive')
    source_group.add_argument('-p', '--platform',
                              help='WebRTC prebuild platform to fetch artifacts for')
    parser.add_argument('-c', '--checksum',
                        help='sha256sum of the unexpanded artifact archive (can be omitted for standard prebuilds)')

    build_mode_group = parser.add_mutually_exclusive_group()
    build_mode_group.add_argument('--debug', action='store_true',
                                  help='Fetch debug prebuild instead of release')
    build_mode_group.add_argument('--release', action='store_false', dest='debug',
                                  help='Fetch release prebuild (default)')

    parser.add_argument('--webrtc-version', metavar='TAG',
                        help='WebRTC tag, used to identify a prebuild (provided implicitly if running through the shell wrapper)')
    parser.add_argument('-o', '--output-dir',
                        required=True,
                        help='Build directory (provided implicitly if running through the shell wrapper)')
    return parser


def download_if_needed(archive_file: str, url: str, checksum: str) -> BinaryIO:
    try:
        f = open(archive_file, 'rb')
        digest = hashlib.sha256()
        chunk = f.read1()
        while chunk:
            digest.update(chunk)
            chunk = f.read1()
        if digest.hexdigest() == checksum.lower():
            return f
        print("existing file '{}' has non-matching checksum {}; re-downloading...".format(archive_file, digest.hexdigest()), file=sys.stderr)
    except FileNotFoundError:
        pass

    print("downloading {}...".format(archive_file), file=sys.stderr)
    try:
        with urllib.request.urlopen(url) as response:
            digest = hashlib.sha256()
            f = open(UNVERIFIED_DOWNLOAD_NAME, 'w+b')
            chunk = response.read1()
            while chunk:
                digest.update(chunk)
                f.write(chunk)
                chunk = response.read1()
            assert digest.hexdigest() == checksum.lower(), "expected {}, actual {}".format(checksum.lower(), digest.hexdigest())
            os.replace(UNVERIFIED_DOWNLOAD_NAME, archive_file)
            return f
    except urllib.error.HTTPError as e:
        print(e, e.filename, file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()
    os.makedirs(os.path.abspath(args.output_dir), exist_ok=True)
    os.chdir(args.output_dir)

    url = args.url
    checksum = args.checksum
    if not url:
        if not args.webrtc_version:
            parser.error(message='--platform requires --webrtc-version')
        platform = resolve_platform(args.platform)
        build_mode = 'debug' if args.debug else 'release'
        url = "https://build-artifacts.signal.org/libraries/webrtc-{}-{}-{}.tar.bz2".format(args.webrtc_version, platform, build_mode)
        if not checksum:
            checksum = PREBUILD_CHECKSUMS[platform]

    if not checksum:
        parser.error(message='missing --checksum')

    archive_file = os.path.basename(url)
    open_archive = download_if_needed(archive_file, url, checksum)

    print("extracting {}...".format(archive_file), file=sys.stderr)
    open_archive.seek(0)
    tarfile.open(fileobj=open_archive).extractall()


main()
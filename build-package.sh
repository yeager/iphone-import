#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu
source_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
output_dir=${1:-"$source_dir/.."}
mkdir -p "$output_dir"
staging=$(mktemp -d)
trap 'rm -rf "$staging"' EXIT

build_package() {
    package_source=$1
    package_name=$2
    package_stage="$staging/$package_name"
    mkdir -p "$package_stage"
    cp -a "$package_source/DEBIAN" "$package_source/usr" "$package_stage"
    locale_dir="$package_stage/usr/share/locale/sv/LC_MESSAGES"
    mkdir -p "$locale_dir"
    msgfmt -o "$locale_dir/$package_name.mo" \
        "$package_stage/usr/share/doc/$package_name/po/sv.po"
    version=$(sed -n 's/^Version: //p' "$package_stage/DEBIAN/control")
    dpkg-deb --root-owner-group --build "$package_stage" "$output_dir/${package_name}_${version}_all.deb"
}

build_package "$source_dir" iphone-import

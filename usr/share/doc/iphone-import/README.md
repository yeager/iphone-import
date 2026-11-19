# iPhone Import

Connect an unlocked iPhone with a USB data cable. Tap **Trust** if prompted. In GNOME Files, select the phone in the device sidebar to browse what it exposes over USB. You can also select the phone in **iPhone Import** and click **Browse iPhone in Files**. The app mounts the phone’s media volume automatically so that DCIM is available, even when GNOME initially lists only the phone’s Documents volume.

To copy photos and videos from DCIM, choose a local destination in **iPhone Import** and click **Import photos and videos**. The app skips identical files, preserves different files with the same name, and leaves originals on the phone. The destination filesystem must support hard links, as ext4 does.

## Build and install

With `gettext` and `dpkg-deb` available, run `./build-package.sh .` and then `sudo apt install ./iphone-import_0.1.2_all.deb`.

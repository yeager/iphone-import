# SPDX-License-Identifier: GPL-3.0-or-later
"""Copy photos and videos from a trusted iOS media volume."""
import hashlib
import os
import stat
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Thread
from urllib.parse import urlsplit

import gettext

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk

locale_dir = Path(__file__).resolve().parents[2] / "share/locale"
translate = gettext.translation("iphone-import", localedir=locale_dir, fallback=True).gettext

MEDIA = {".heic", ".heif", ".jpg", ".jpeg", ".png", ".gif", ".tif", ".tiff",
         ".dng", ".mov", ".mp4", ".m4v", ".avi", ".webp", ".avif"}
CHUNK_SIZE = 1024 * 1024


def media_files(directory, cancellable):
    entries = directory.enumerate_children(
        "standard::name,standard::type", Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS,
        cancellable)
    try:
        while info := entries.next_file(cancellable):
            name = info.get_name()
            if name in {"", ".", ".."} or "/" in name:
                continue
            child = directory.get_child(name)
            if info.get_file_type() == Gio.FileType.DIRECTORY:
                yield from media_files(child, cancellable)
            elif info.get_file_type() == Gio.FileType.REGULAR and Path(name).suffix.lower() in MEDIA:
                yield child, name
    finally:
        entries.close(None)


def same_content(path, size, expected, cancellable):
    try:
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        with os.fdopen(os.open(path, flags), "rb") as file:
            info = os.fstat(file.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size != size:
                return False
            digest = hashlib.sha256()
            while block := file.read(CHUNK_SIZE):
                if cancellable.is_cancelled():
                    return False
                digest.update(block)
            return digest.hexdigest() == expected
    except OSError:
        return False


def import_file(source, name, destination, cancellable):
    digest = hashlib.sha256()
    with NamedTemporaryFile(dir=destination, prefix=".iphone-import-") as staging:
        stream = source.read(cancellable)
        try:
            while data := stream.read_bytes(CHUNK_SIZE, cancellable).get_data():
                staging.write(data)
                digest.update(data)
        finally:
            stream.close(None)
        staging.flush()
        digest_value = digest.hexdigest()
        path = Path(name)
        # Prefer the original name. Keep both if iOS reuses a filename.
        count = 0
        while not cancellable.is_cancelled():
            if count == 0:
                candidate = destination / name
            else:
                disambiguator = f"-{digest_value[:12]}" + (f"-{count}" if count > 1 else "")
                suffix = disambiguator + path.suffix
                stem = os.fsencode(path.stem)[:240 - len(os.fsencode(suffix))]
                candidate = destination / (stem.decode("utf-8", errors="ignore") + suffix)
            try:
                os.link(staging.name, candidate)
                return True
            except FileExistsError:
                if same_content(candidate, staging.tell(), digest_value, cancellable):
                    return False
                count += 1
    return False


class ImportWindow(Gtk.ApplicationWindow):
    def __init__(self, application):
        super().__init__(application=application, title=translate("Import from iPhone"),
                         default_width=510)
        self.monitor = Gio.VolumeMonitor.get()
        self.devices = []
        self.destination = None
        self.cancellable = None
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for edge in ("top", "bottom", "start", "end"):
            getattr(panel, f"set_margin_{edge}")(20)
        self.set_child(panel)
        panel.append(Gtk.Label(label=translate(
            "Connect and unlock your iPhone. Tap Trust if prompted. "
            "Import copies photos and videos and leaves originals on your iPhone."),
            xalign=0, wrap=True))
        self.device = Gtk.DropDown.new_from_strings([])
        self.device.connect("notify::selected", self.update_buttons)
        panel.append(self.device)
        self.no_device = Gtk.Label(
            label=translate("No iPhone detected. Try reconnecting it while it is unlocked."),
            xalign=0, wrap=True)
        panel.append(self.no_device)
        self.browse = self.button(panel, translate("Browse iPhone in Files"), self.browse_device)
        self.location = Gtk.Label(xalign=0, selectable=True, wrap=True)
        panel.append(self.location)
        self.choose = self.button(panel, translate("Choose destination"), self.choose_destination)
        self.import_button = self.button(panel, translate("Import photos and videos"), self.start_import)
        self.cancel = self.button(panel, translate("Cancel import"), self.cancel_import)
        self.open = self.button(panel, translate("Open destination"), self.open_destination)
        self.status = Gtk.Label(xalign=0, wrap=True, selectable=True)
        panel.append(self.status)
        for signal in ("volume-added", "volume-removed", "volume-changed"):
            self.monitor.connect_object(signal, self.refresh_devices, self)
        self.connect("close-request", self.close_window)
        self.refresh_devices()

    @staticmethod
    def button(panel, label, callback):
        button = Gtk.Button(label=label)
        button.connect("clicked", callback)
        panel.append(button)
        return button

    def refresh_devices(self, *_):
        selected = self.device.get_selected()
        previous = self.devices[selected][1] if selected < len(self.devices) else None
        devices = []
        for volume in self.monitor.get_volumes():
            root = volume.get_activation_root()
            if root and root.get_uri_scheme() == "afc" and urlsplit(root.get_uri()).port is None:
                devices.append((volume.get_name(), root.get_uri()))
        devices.sort()
        if devices != self.devices:
            self.devices = devices
            self.device.set_model(Gtk.StringList.new([name for name, _ in devices]))
            selected = next((i for i, (_, uri) in enumerate(devices) if uri == previous), 0)
            if devices:
                self.device.set_selected(selected)
        self.device.set_visible(bool(devices))
        self.no_device.set_visible(not devices)
        self.update_buttons()

    def update_buttons(self, *_):
        busy = self.cancellable is not None
        self.choose.set_sensitive(not busy)
        self.device.set_sensitive(not busy)
        has_device = self.device.get_selected() < len(self.devices)
        self.browse.set_sensitive(not busy and has_device)
        self.import_button.set_sensitive(not busy and has_device and self.destination is not None)
        self.cancel.set_visible(busy)
        self.open.set_sensitive(self.destination is not None)
        self.location.set_text(str(self.destination) if self.destination else
                               translate("Choose a local folder for imported files."))

    def choose_destination(self, *_):
        dialog = Gtk.FileDialog(title=translate("Choose destination"))
        dialog.select_folder(self, None, self.destination_selected)

    def destination_selected(self, dialog, result):
        try:
            path = dialog.select_folder_finish(result).get_path()
            if path is None:
                self.status.set_text(translate("Choose a local folder for imported files."))
                return
            self.destination = Path(path)
            self.update_buttons()
        except GLib.Error as error:
            if not error.matches(Gtk.dialog_error_quark(), Gtk.DialogError.DISMISSED):
                self.status.set_text(translate("Could not select the destination folder."))

    def browse_device(self, *_):
        self.connect_device(self.browse_mounted)

    def start_import(self, *_):
        self.connect_device(self.import_mounted)

    def connect_device(self, callback):
        source = Gio.File.new_for_uri(self.devices[self.device.get_selected()][1])
        self.cancellable = Gio.Cancellable()
        self.update_buttons()
        self.status.set_text(translate("Connecting to iPhone…"))
        source.mount_enclosing_volume(Gio.MountMountFlags.NONE, Gtk.MountOperation.new(self),
                                      self.cancellable, callback)

    def mount_device(self, source, result):
        try:
            source.mount_enclosing_volume_finish(result)
        except GLib.Error as error:
            if not error.matches(Gio.io_error_quark(), Gio.IOErrorEnum.ALREADY_MOUNTED):
                raise

    def browse_mounted(self, source, result):
        try:
            self.mount_device(source, result)
            Gio.AppInfo.launch_default_for_uri(source.get_uri(), self.cancellable)
            self.status.set_text("")
        except GLib.Error as error:
            if self.cancellable.is_cancelled():
                self.status.set_text("")
            else:
                self.status.set_text(error.message)
        finally:
            self.cancellable = None
            self.update_buttons()

    def import_mounted(self, source, result):
        try:
            self.mount_device(source, result)
        except GLib.Error as error:
            self.finish_import(0, 0, error)
            return
        Thread(target=self.copy_media, args=(source.get_child("DCIM"), self.destination,
                                            self.cancellable), daemon=True).start()

    def copy_media(self, source, destination, cancellable):
        imported = skipped = 0
        error = None
        try:
            for item, name in media_files(source, cancellable):
                if cancellable.is_cancelled():
                    break
                if import_file(item, name, destination, cancellable):
                    imported += 1
                elif not cancellable.is_cancelled():
                    skipped += 1
                if (imported + skipped) % 10 == 0:
                    GLib.idle_add(self.show_progress, imported, skipped)
        except (GLib.Error, OSError) as exc:
            error = exc
        GLib.idle_add(self.finish_import, imported, skipped, error)

    def show_progress(self, imported, skipped):
        self.status.set_text(translate("Imported: {imported} · Duplicates skipped: {skipped}")
                             .format(imported=imported, skipped=skipped))

    def finish_import(self, imported, skipped, error):
        cancelled = self.cancellable.is_cancelled()
        self.cancellable = None
        self.update_buttons()
        self.show_progress(imported, skipped)
        if cancelled:
            self.status.set_text(translate("Import cancelled.") + "\n" + self.status.get_text())
        elif error:
            message = translate("Import stopped. Check the iPhone connection and destination.")
            self.status.set_text(f"{message}\n{error.message if isinstance(error, GLib.Error) else error}\n"
                                 + self.status.get_text())

    def cancel_import(self, *_):
        if self.cancellable:
            self.cancellable.cancel()

    def close_window(self, *_):
        if self.cancellable:
            self.cancel_import()
            return True
        return False

    def open_destination(self, *_):
        try:
            Gio.AppInfo.launch_default_for_uri(self.destination.as_uri(), None)
        except GLib.Error:
            self.status.set_text(translate("Could not open the destination folder."))


def main():
    application = Gtk.Application(application_id="io.github.yeager.IPhoneImport")
    application.connect("activate", lambda app: (
        app.get_active_window() or ImportWindow(app)).present())
    return application.run()


if __name__ == "__main__":
    raise SystemExit(main())

import 'dart:async';

import 'package:flet/flet.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:receive_sharing_intent/receive_sharing_intent.dart';

/// Registered by `flet build` as `ytmpd_android.Extension()`.
class Extension extends FletExtension {
  @override
  FletService? createService(Control control) {
    switch (control.type) {
      case "ShareReceiver":
        return ShareReceiverService(control: control);
      case "KeepAlive":
        return KeepAliveService(control: control);
      default:
        return null;
    }
  }
}

/// Hands text shared to the app (Android's Share menu) to Python: at startup through `get_initial`,
/// afterwards through the `shared` event.
class ShareReceiverService extends FletService {
  ShareReceiverService({required super.control});

  StreamSubscription<List<SharedMediaFile>>? _subscription;

  @override
  void init() {
    super.init();
    control.addInvokeMethodListener(_invokeMethod);
    _subscription = ReceiveSharingIntent.instance.getMediaStream().listen((files) {
      final text = _text(files);
      if (text != null) {
        control.triggerEvent("shared", text);
      }
    });
  }

  static String? _text(List<SharedMediaFile> files) {
    for (final file in files) {
      if (file.type == SharedMediaType.text || file.type == SharedMediaType.url) {
        return file.path; // for text, the plugin puts the text itself in `path`
      }
    }
    return null;
  }

  Future<dynamic> _invokeMethod(String name, dynamic args) async {
    switch (name) {
      case "get_initial":
        final text = _text(await ReceiveSharingIntent.instance.getInitialMedia());
        await ReceiveSharingIntent.instance.reset(); // don't hand the same share over twice
        return text;
      default:
        throw Exception("Unknown ShareReceiver method: $name");
    }
  }

  @override
  void dispose() {
    control.removeInvokeMethodListener(_invokeMethod);
    _subscription?.cancel();
    super.dispose();
  }
}

/// A "data sync" foreground service with a progress notification. It runs no task of its own: being in the
/// foreground keeps the process, and with allowWakeLock the CPU, alive while Python downloads with the screen off.
class KeepAliveService extends FletService {
  KeepAliveService({required super.control});

  @override
  void init() {
    super.init();
    control.addInvokeMethodListener(_invokeMethod);
  }

  Future<dynamic> _invokeMethod(String name, dynamic args) async {
    switch (name) {
      case "start":
        // Android 13+: without this permission the service still runs, but its notification isn't shown.
        if (await FlutterForegroundTask.checkNotificationPermission() != NotificationPermission.granted) {
          await FlutterForegroundTask.requestNotificationPermission();
        }
        FlutterForegroundTask.init(
          androidNotificationOptions: AndroidNotificationOptions(
            channelId: "downloads",
            channelName: args["channel"],
            onlyAlertOnce: true,
          ),
          iosNotificationOptions: const IOSNotificationOptions(),
          foregroundTaskOptions: ForegroundTaskOptions(
            eventAction: ForegroundTaskEventAction.nothing(),
            allowWakeLock: true,
            allowWifiLock: true,
            stopWithTask: true,
          ),
        );
        final result = await FlutterForegroundTask.startService(
          serviceTypes: [ForegroundServiceTypes.dataSync],
          notificationTitle: args["title"],
          notificationText: args["text"],
        );
        return result is ServiceRequestSuccess;
      case "update":
        await FlutterForegroundTask.updateService(notificationTitle: args["title"], notificationText: args["text"]);
        return null;
      case "stop":
        await FlutterForegroundTask.stopService();
        return null;
      default:
        throw Exception("Unknown KeepAlive method: $name");
    }
  }

  @override
  void dispose() {
    control.removeInvokeMethodListener(_invokeMethod);
    super.dispose();
  }
}

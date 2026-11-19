import 'dart:async';

import 'package:flet/flet.dart';
import 'package:receive_sharing_intent/receive_sharing_intent.dart';

/// Registered by `flet build` as `ytmpd_share.Extension()`.
class Extension extends FletExtension {
  @override
  FletService? createService(Control control) {
    switch (control.type) {
      case "ShareReceiver":
        return ShareReceiverService(control: control);
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

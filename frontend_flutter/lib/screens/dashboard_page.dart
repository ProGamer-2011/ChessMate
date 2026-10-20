import 'package:flutter/material.dart';

import '../services/backend_api.dart';
import '../widgets/status_card.dart';

class DashboardPage extends StatefulWidget {
  const DashboardPage({super.key, required this.api});

  final BackendApi api;

  @override
  State<DashboardPage> createState() => _DashboardPageState();
}

class _DashboardPageState extends State<DashboardPage> {
  bool _loading = true;
  bool _backendOnline = false;
  String _error = '';

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = '';
    });

    try {
      final online = await widget.api.healthCheck();
      setState(() {
        _backendOnline = online;
      });
    } catch (error) {
      setState(() {
        _backendOnline = false;
        _error = error.toString();
      });
    } finally {
      setState(() {
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('ChessMate Flutter Shell', style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(height: 8),
          Text(
            'Shared UI entrypoint for web, mobile, and desktop. Python logic runs behind HTTP services.',
            style: Theme.of(context).textTheme.bodyMedium,
          ),
          const SizedBox(height: 16),
          if (_loading)
            const LinearProgressIndicator()
          else
            StatusCard(
              title: 'Backend Service',
              subtitle: 'GET /health from Python service',
              status: _backendOnline ? 'Online' : 'Offline',
            ),
          if (_error.isNotEmpty) ...[
            const SizedBox(height: 12),
            Text(_error, style: const TextStyle(color: Colors.redAccent)),
          ],
          const SizedBox(height: 16),
          FilledButton.icon(
            onPressed: _load,
            icon: const Icon(Icons.refresh),
            label: const Text('Recheck Backend'),
          ),
        ],
      ),
    );
  }
}

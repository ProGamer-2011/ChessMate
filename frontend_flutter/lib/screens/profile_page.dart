import 'package:flutter/material.dart';

import '../models/profile.dart';
import '../services/backend_api.dart';

class ProfilePage extends StatefulWidget {
  const ProfilePage({super.key, required this.api});

  final BackendApi api;

  @override
  State<ProfilePage> createState() => _ProfilePageState();
}

class _ProfilePageState extends State<ProfilePage> {
  ChessMateProfile? _profile;
  bool _loading = true;
  String _error = '';

  @override
  void initState() {
    super.initState();
    _loadProfile();
  }

  Future<void> _loadProfile() async {
    setState(() {
      _loading = true;
      _error = '';
    });

    try {
      final profile = await widget.api.fetchProfile();
      setState(() {
        _profile = profile;
      });
    } catch (error) {
      setState(() {
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
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_error.isNotEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(_error, style: const TextStyle(color: Colors.redAccent)),
              const SizedBox(height: 12),
              FilledButton(onPressed: _loadProfile, child: const Text('Retry')),
            ],
          ),
        ),
      );
    }

    final profile = _profile;
    if (profile == null) {
      return const Center(child: Text('No profile loaded'));
    }

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Card(
          child: ListTile(
            title: Text(profile.name.isEmpty ? 'Unknown Player' : profile.name),
            subtitle: Text('Chess.com: ${profile.chessComUsername.isEmpty ? 'Not connected' : profile.chessComUsername}'),
            trailing: Text('Elo ${profile.rating}'),
          ),
        ),
        Card(
          child: ListTile(
            title: const Text('Personality'),
            subtitle: Text(profile.personalityName.isEmpty ? 'Not set' : profile.personalityName),
            trailing: Text('Style: ${profile.styleName.isEmpty ? '-' : profile.styleName}'),
          ),
        ),
        Card(
          child: ListTile(
            title: const Text('Confidence'),
            subtitle: const Text('Current personalization confidence'),
            trailing: Text('${profile.confidence}%'),
          ),
        ),
      ],
    );
  }
}

import 'package:flutter/material.dart';

class AnalysisPage extends StatelessWidget {
  const AnalysisPage({super.key});

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: const [
        Card(
          child: ListTile(
            title: Text('Chess.com Sync + Analysis'),
            subtitle: Text('Next milestone: trigger sync and profile build through Python API endpoints.'),
          ),
        ),
      ],
    );
  }
}

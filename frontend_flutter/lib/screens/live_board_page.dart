import 'package:flutter/material.dart';

class LiveBoardPage extends StatelessWidget {
  const LiveBoardPage({super.key});

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: const [
        Card(
          child: ListTile(
            title: Text('Live Board / Modes'),
            subtitle: Text('Next milestone: wire Coach Mode and Win Mode controls to backend commands.'),
          ),
        ),
      ],
    );
  }
}

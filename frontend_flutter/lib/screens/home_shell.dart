import 'package:flutter/material.dart';

import '../services/backend_api.dart';
import 'analysis_page.dart';
import 'dashboard_page.dart';
import 'live_board_page.dart';
import 'profile_page.dart';

class HomeShell extends StatefulWidget {
  const HomeShell({super.key});

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  final BackendApi _api = BackendApi();
  int _index = 0;

  @override
  Widget build(BuildContext context) {
    final pages = [
      DashboardPage(api: _api),
      ProfilePage(api: _api),
      const AnalysisPage(),
      const LiveBoardPage(),
    ];

    return Scaffold(
      appBar: AppBar(title: const Text('ChessMate')),
      body: pages[_index],
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (value) => setState(() => _index = value),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.home_outlined), label: 'Home'),
          NavigationDestination(icon: Icon(Icons.person_outline), label: 'Profile'),
          NavigationDestination(icon: Icon(Icons.auto_graph_outlined), label: 'Analysis'),
          NavigationDestination(icon: Icon(Icons.sports_esports_outlined), label: 'Live'),
        ],
      ),
    );
  }
}

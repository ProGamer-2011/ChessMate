import 'package:flutter/material.dart';

import 'screens/home_shell.dart';

class ChessMateApp extends StatelessWidget {
  const ChessMateApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'ChessMate',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF2563EB), brightness: Brightness.dark),
        useMaterial3: true,
      ),
      home: const HomeShell(),
    );
  }
}

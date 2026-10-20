import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/profile.dart';

class BackendApi {
  BackendApi({http.Client? client}) : _client = client ?? http.Client();

  final http.Client _client;

  static const String _defaultBaseUrl = 'http://127.0.0.1:8000';
  String get baseUrl => const String.fromEnvironment('CHESSMATE_API_BASE_URL', defaultValue: _defaultBaseUrl);

  Uri _uri(String path) => Uri.parse('$baseUrl$path');

  Future<bool> healthCheck() async {
    final response = await _client.get(_uri('/health'));
    return response.statusCode == 200;
  }

  Future<ChessMateProfile> fetchProfile() async {
    final response = await _client.get(_uri('/profile'));

    if (response.statusCode != 200) {
      throw Exception('Failed to fetch profile: ${response.statusCode}');
    }

    final body = jsonDecode(response.body) as Map<String, dynamic>;
    return ChessMateProfile.fromJson(body['profile'] as Map<String, dynamic>);
  }
}

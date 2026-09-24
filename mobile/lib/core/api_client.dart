import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:supabase_flutter/supabase_flutter.dart';

import 'app_config.dart';

class ApiException implements Exception {
  ApiException(this.message, {this.statusCode});
  final String message;
  final int? statusCode;

  @override
  String toString() => message;
}

class ApiClient {
  ApiClient({http.Client? client}) : _client = client ?? http.Client();
  final http.Client _client;

  Future<Map<String, dynamic>> get(String path) => _request('GET', path);

  Future<Map<String, dynamic>> post(
    String path, {
    Map<String, dynamic>? body,
  }) =>
      _request('POST', path, body: body);

  Future<Map<String, dynamic>> delete(String path) => _request('DELETE', path);

  Future<Map<String, dynamic>> _request(
    String method,
    String path, {
    Map<String, dynamic>? body,
  }) async {
    final token = Supabase.instance.client.auth.currentSession?.accessToken;
    if (token == null) {
      throw ApiException('로그인이 필요합니다.', statusCode: 401);
    }

    final uri = Uri.parse('${AppConfig.apiBaseUrl}$path');
    final headers = <String, String>{
      'Authorization': 'Bearer $token',
      'Content-Type': 'application/json',
    };

    late http.Response response;
    if (method == 'POST') {
      response = await _client.post(
        uri,
        headers: headers,
        body: jsonEncode(body ?? const <String, dynamic>{}),
      );
    } else if (method == 'DELETE') {
      response = await _client.delete(uri, headers: headers);
    } else {
      response = await _client.get(uri, headers: headers);
    }

    Map<String, dynamic> decoded = <String, dynamic>{};
    if (response.body.isNotEmpty) {
      try {
        final value = jsonDecode(response.body);
        if (value is Map<String, dynamic>) {
          decoded = value;
        }
      } on FormatException {
        if (response.statusCode >= 200 && response.statusCode < 300) {
          throw ApiException(
            '서버 응답 형식이 올바르지 않습니다.',
            statusCode: response.statusCode,
          );
        }
      }
    }

    if (response.statusCode < 200 || response.statusCode >= 300) {
      final detail = decoded['detail'];
      throw ApiException(
        detail is String
            ? detail
            : '서버에서 요청을 처리하지 못했습니다. (${response.statusCode})',
        statusCode: response.statusCode,
      );
    }
    return decoded;
  }
}

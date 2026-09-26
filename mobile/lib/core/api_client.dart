import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:supabase_flutter/supabase_flutter.dart';

import 'app_config.dart';

class ApiException implements Exception {
  ApiException(
    this.message, {
    this.statusCode,
    this.isTransient = false,
  });

  final String message;
  final int? statusCode;
  final bool isTransient;

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

  Future<String> _accessToken({bool forceRefresh = false}) async {
    final auth = Supabase.instance.client.auth;
    var session = auth.currentSession;
    if (session == null) {
      throw ApiException('로그인이 필요합니다.', statusCode: 401);
    }

    final expiresAt = session.expiresAt;
    final nowSeconds = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    final shouldRefresh = forceRefresh ||
        (expiresAt != null && expiresAt <= nowSeconds + 60);

    if (shouldRefresh) {
      try {
        final refreshed = await auth.refreshSession();
        session = refreshed.session ?? auth.currentSession;
      } on AuthException {
        if (auth.currentSession == null) {
          throw ApiException(
            '로그인 세션이 만료되었습니다. 다시 로그인해 주세요.',
            statusCode: 401,
          );
        }
        throw ApiException(
          '로그인 세션을 갱신하지 못했습니다. 잠시 후 다시 시도해 주세요.',
          statusCode: 401,
          isTransient: true,
        );
      } on SocketException {
        throw ApiException(
          '네트워크 연결이 불안정해 로그인 세션을 갱신하지 못했습니다.',
          isTransient: true,
        );
      } on TimeoutException {
        throw ApiException(
          '로그인 세션 갱신 시간이 초과되었습니다.',
          isTransient: true,
        );
      }

      if (session == null) {
        throw ApiException(
          '로그인 세션이 만료되었습니다. 다시 로그인해 주세요.',
          statusCode: 401,
        );
      }
    }

    return session.accessToken;
  }

  Future<http.Response> _send(
    String method,
    Uri uri,
    Map<String, String> headers,
    Map<String, dynamic>? body,
  ) {
    if (method == 'POST') {
      return _client.post(
        uri,
        headers: headers,
        body: jsonEncode(body ?? const <String, dynamic>{}),
      );
    }
    if (method == 'DELETE') {
      return _client.delete(uri, headers: headers);
    }
    return _client.get(uri, headers: headers);
  }

  Future<Map<String, dynamic>> _request(
    String method,
    String path, {
    Map<String, dynamic>? body,
  }) async {
    final uri = Uri.parse('${AppConfig.apiBaseUrl}$path');

    for (var authAttempt = 0; authAttempt < 2; authAttempt++) {
      final token = await _accessToken(forceRefresh: authAttempt > 0);
      final headers = <String, String>{
        'Authorization': 'Bearer $token',
        'Content-Type': 'application/json',
      };

      late http.Response response;
      try {
        response = await _send(method, uri, headers, body).timeout(
          const Duration(seconds: 25),
        );
      } on SocketException {
        throw ApiException(
          '서버 주소를 확인하지 못했습니다. 네트워크 연결을 확인해 주세요.',
          isTransient: true,
        );
      } on http.ClientException {
        throw ApiException(
          '서버에 연결할 수 없습니다. 네트워크 연결을 확인해 주세요.',
          isTransient: true,
        );
      } on TimeoutException {
        throw ApiException(
          '서버 응답이 지연되고 있습니다. 잠시 후 다시 시도해 주세요.',
          isTransient: true,
        );
      }

      if (response.statusCode == 401 && authAttempt == 0) {
        continue;
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
          isTransient: response.statusCode >= 500,
        );
      }
      return decoded;
    }

    throw ApiException(
      '로그인 세션을 갱신하지 못했습니다. 다시 로그인해 주세요.',
      statusCode: 401,
    );
  }
}

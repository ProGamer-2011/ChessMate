class ChessMateProfile {
  const ChessMateProfile({
    required this.name,
    required this.rating,
    required this.personalityName,
    required this.styleName,
    required this.chessComUsername,
    required this.confidence,
  });

  final String name;
  final int rating;
  final String personalityName;
  final String styleName;
  final String chessComUsername;
  final int confidence;

  factory ChessMateProfile.fromJson(Map<String, dynamic> json) {
    return ChessMateProfile(
      name: (json['name'] ?? '') as String,
      rating: (json['rating'] ?? 1000) as int,
      personalityName: (json['personality_name'] ?? '') as String,
      styleName: (json['style_name'] ?? '') as String,
      chessComUsername: (json['chesscom_username'] ?? '') as String,
      confidence: (json['confidence'] ?? 20) as int,
    );
  }
}

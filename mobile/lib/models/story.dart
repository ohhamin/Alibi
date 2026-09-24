class StoryCharacter {
  const StoryCharacter({
    required this.id,
    required this.displayName,
    required this.roleLabel,
    required this.publicBio,
    required this.isPlayerSelectable,
  });

  final String id;
  final String displayName;
  final String roleLabel;
  final String publicBio;
  final bool isPlayerSelectable;

  factory StoryCharacter.fromJson(Map<String, dynamic> json) => StoryCharacter(
        id: json['id'] as String,
        displayName: json['display_name'] as String? ?? '',
        roleLabel: json['role_label'] as String? ?? '',
        publicBio: json['public_bio'] as String? ?? '',
        isPlayerSelectable: json['is_player_selectable'] as bool? ?? false,
      );
}

class Story {
  const Story({
    required this.storyVersionId,
    required this.title,
    required this.synopsis,
    required this.difficulty,
    required this.estimatedMinutes,
    required this.characters,
  });

  final String storyVersionId;
  final String title;
  final String synopsis;
  final String difficulty;
  final int? estimatedMinutes;
  final List<StoryCharacter> characters;

  factory Story.fromJson(Map<String, dynamic> json) => Story(
        storyVersionId: json['story_version_id'] as String,
        title: json['title'] as String? ?? '',
        synopsis: json['synopsis'] as String? ?? '',
        difficulty: json['difficulty'] as String? ?? 'normal',
        estimatedMinutes: json['estimated_minutes'] as int?,
        characters: ((json['characters'] as List?) ?? const [])
            .map((e) => StoryCharacter.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}

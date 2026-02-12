from django.db import models
from django.utils import timezone

class GameRecord(models.Model):
    GAME_CHOICES = [
        ('2048', '2048'),
        ('wordle', 'Wordle'),
        ('reaction', 'Reaction Speed'),
    ]

    game_type = models.CharField(max_length=20, choices=GAME_CHOICES, default='2048')
    player_name = models.CharField(max_length=10)
    score = models.IntegerField()  # 2048은 점수, 반응속도는 ms
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-score', '-created_at'] # 기본은 점수 높은 순

    def __str__(self):
        return f"{self.game_type} - {self.player_name}: {self.score}"
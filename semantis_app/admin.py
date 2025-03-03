from django.contrib import admin
from .models import Judgment, Statute, SearchHistory, SavedCase, ScoringSection, ScoreValidation, UserProfile

# Register your models here.
admin.site.register(Judgment)
admin.site.register(Statute)
admin.site.register(SearchHistory)
admin.site.register(SavedCase)
admin.site.register(ScoringSection)
admin.site.register(ScoreValidation)
admin.site.register(UserProfile)

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from core.menu_lock import lock_menu
from apps.menu.models import Category, Unit, Dish, Combo, MenuActivityLog
from apps.menu.english_catalog import CATEGORY_NAMES, UNIT_NAMES, DISH_NAMES, COMBO_TRANSLATIONS, known_name


class Command(BaseCommand):
    help = "Fill blank English fields for the known public catalog; preserve existing translations, prices and orders."

    @transaction.atomic
    def handle(self, *args, **options):
        lock_menu()
        count = 0
        for model,names,entity in ((Category,CATEGORY_NAMES,"CATEGORY"),(Unit,UNIT_NAMES,"UNIT"),(Dish,DISH_NAMES,"DISH"),(Combo,{},"COMBO")):
            for item in model.objects.select_for_update().all():
                changes = {}
                translated = known_name(names,item.name)
                description = "A familiar favourite, prepared with care in the Cơm Quê kitchen." if entity=="DISH" and translated else ""
                if entity=="COMBO" and item.code in COMBO_TRANSLATIONS:
                    translated,description = COMBO_TRANSLATIONS[item.code]
                if translated and not item.name_en:
                    changes["name_en"] = translated
                if description and not getattr(item,"description_en", "existing"):
                    changes["description_en"] = description
                if changes:
                    model.objects.filter(pk=item.pk).update(**changes,revision=F("revision")+1,updated_at=timezone.now())
                    MenuActivityLog.objects.create(entity=entity,object_id=item.pk,label_snapshot=str(item)[:180],
                        action="Bổ sung tiếng Anh",description="Chỉ bổ sung ô tiếng Anh đang trống; giữ nguyên tên Việt, giá và trạng thái.",actor_snapshot="seed_menu_english")
                    count += 1
        self.stdout.write(f"English catalog fields filled: {count} records. Existing translations and financial data preserved.")

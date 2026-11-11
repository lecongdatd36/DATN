"""Starter translations for the existing public catalog; managers can edit them."""
CATEGORY_NAMES = {"Món chính":"Main dishes", "Khai vị":"Starters", "Món rau":"Vegetables", "Đồ uống":"Drinks", "Tráng miệng":"Desserts"}
UNIT_NAMES = {"Phần":"Serving", "Đĩa":"Plate", "Ly":"Glass", "Chai":"Bottle", "Lon":"Can", "Tô":"Bowl", "Bát":"Bowl"}
DISH_NAMES = {
    "Cơm gà xối mỡ":"Crispy Fried Chicken with Rice", "Cơm sườn nướng":"Grilled Pork Chop with Rice",
    "Phở bò đặc biệt":"Special Beef Pho", "Bún chả Hà Nội":"Hanoi Grilled Pork with Vermicelli",
    "Tôm rang me":"Tamarind Prawns", "Trứng chiên thịt":"Minced Meat Omelette",
    "Rau củ luộc kho quẹt":"Boiled Vegetables with Savoury Dip", "Rau muống xào tỏi":"Garlic Stir-Fried Morning Glory",
    "Trà chanh":"Lemon Tea", "Cà phê sữa đá":"Vietnamese Iced Coffee with Milk", "Nước ngọt Coca":"Coca-Cola",
    "Bia lon Sài Gòn Lager":"Saigon Lager Beer (Can)", "Chả giò hải sản":"Seafood Spring Rolls",
    "Gỏi cuốn tôm thịt":"Fresh Shrimp and Pork Rolls", "Chè khúc bạch":"Khuc Bach Sweet Dessert", "Trái cây theo mùa":"Seasonal Fruit",
}
COMBO_TRANSLATIONS = {
    "CB_HENHO": ("A Taste of Home for Two", "A comforting meal for two, with rice dishes and refreshing tea."),
    "CB_SUMVAY": ("Family Gathering for Four", "Rice, crisp spring rolls and tea for four around the table."),
    "CB_BANBE": ("Good Company for Six", "Rice, fresh rolls and lemon tea to share with friends."),
}


def known_name(mapping, name):
    return next((value for key,value in mapping.items() if key.casefold()==name.strip().casefold()), "")

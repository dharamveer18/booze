from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    Address,
    Category,
    Customer,
    DeliveryPartner,
    Order,
    OrderItem,
    Product,
    RetailShop,
    ShopOwner,
    ShopProduct,
    User,
)


@admin.register(User)
class BoozeUserAdmin(UserAdmin):
    list_display = ["username", "first_name", "last_name", "phone", "role", "is_active"]
    list_filter = ["role", "is_active", "is_superuser"]
    search_fields = ["username", "first_name", "last_name", "phone", "email"]
    fieldsets = UserAdmin.fieldsets + (("Booze", {"fields": ["role", "phone"]}),)


class AddressInline(admin.TabularInline):
    model = Address
    extra = 0


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ["__str__", "date_of_birth", "is_age_verified", "created_at"]
    list_filter = ["is_age_verified"]
    search_fields = ["user__phone", "user__first_name", "user__last_name", "user__username"]
    inlines = [AddressInline]


@admin.register(ShopOwner)
class ShopOwnerAdmin(admin.ModelAdmin):
    list_display = ["business_name", "user", "is_kyc_verified"]
    list_filter = ["is_kyc_verified"]
    search_fields = ["business_name", "user__phone"]


@admin.register(DeliveryPartner)
class DeliveryPartnerAdmin(admin.ModelAdmin):
    list_display = ["__str__", "vehicle_number", "is_verified", "is_online", "rating"]
    list_filter = ["is_verified", "is_online", "vehicle_type"]
    search_fields = ["user__phone", "vehicle_number", "user__first_name"]


@admin.register(RetailShop)
class RetailShopAdmin(admin.ModelAdmin):
    list_display = ["name", "city", "licence_number", "licence_valid_till", "is_licence_verified", "is_active"]
    list_filter = ["city", "is_licence_verified", "is_active"]
    search_fields = ["name", "licence_number", "pincode"]


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "emoji", "bottle_shape", "sort_order"]
    prepopulated_fields = {"slug": ["name"]}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["name", "brand", "category", "volume_ml", "abv", "mrp", "is_active"]
    list_filter = ["category", "is_active"]
    search_fields = ["name", "brand"]


@admin.register(ShopProduct)
class ShopProductAdmin(admin.ModelAdmin):
    list_display = ["product", "shop", "price", "stock", "is_available"]
    list_filter = ["shop", "is_available", "product__category"]
    list_editable = ["price", "stock", "is_available"]
    search_fields = ["product__name"]


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ["product_name", "volume_ml", "price", "quantity"]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["order_number", "customer", "shop", "status", "grand_total", "payment_status", "created_at"]
    list_filter = ["status", "payment_status", "shop"]
    search_fields = ["order_number", "customer__user__phone"]
    readonly_fields = ["order_number", "delivery_otp"]
    inlines = [OrderItemInline]

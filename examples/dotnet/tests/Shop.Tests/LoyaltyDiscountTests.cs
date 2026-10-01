using NUnit.Framework;

namespace Shop.Tests;

public class LoyaltyDiscountTests
{
    [Test]
    public void Given_new_customer_When_applying_Should_keep_price()
    {
        Assert.That(LoyaltyDiscount.Apply(100m, 0), Is.EqualTo(100m));
    }

    [Test]
    public void Given_veteran_customer_When_applying_Should_give_ten_percent()
    {
        Assert.That(LoyaltyDiscount.Apply(100m, 10), Is.EqualTo(90m));
    }
}

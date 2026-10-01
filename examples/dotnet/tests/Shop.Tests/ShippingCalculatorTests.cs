using NUnit.Framework;

namespace Shop.Tests;

public class ShippingCalculatorTests
{
    [Test]
    public void Given_small_light_order_When_calculating_Should_charge_standard_rate()
    {
        Assert.That(ShippingCalculator.Calculate(50m, 1m), Is.EqualTo(4.90m));
    }

    [Test]
    public void Given_large_order_When_calculating_Should_ship_for_free()
    {
        Assert.That(ShippingCalculator.Calculate(250m, 1m), Is.EqualTo(0m));
    }

    [Test]
    public void Given_negative_total_When_calculating_Should_throw()
    {
        Assert.Throws<ArgumentOutOfRangeException>(() => ShippingCalculator.Calculate(-1m, 1m));
    }

    [Test]
    public void Given_heavy_parcel_When_calculating_Should_add_surcharge()
    {
        Assert.That(ShippingCalculator.Calculate(50m, 30m), Is.EqualTo(12.40m));
    }
}

import SwiperCore from 'swiper/core';
import { liveSwiper } from './swiperInstance';

const mountSwiper = () => {
    const el = document.createElement('div');
    el.innerHTML = '<div class="swiper-wrapper"><div class="swiper-slide"></div><div class="swiper-slide"></div></div>';
    document.body.appendChild(el);
    return new SwiperCore(el, {});
};

describe('liveSwiper', () => {
    test('returns nothing before a layout has registered a Swiper', () => {
        expect(liveSwiper(null)).toBeNull();
        expect(liveSwiper(undefined)).toBeNull();
    });

    test('returns a mounted Swiper so layouts can move between slides', () => {
        const swiper = mountSwiper();
        expect(liveSwiper(swiper)).toBe(swiper);
        swiper.destroy(true, false);
    });

    test('ignores the Swiper a rotated-away layout destroyed', () => {
        const swiper = mountSwiper();
        // The unmounting layout's Swiper component calls exactly this.
        swiper.destroy(true, false);

        // The original failure: the next layout called slideTo on the destroyed instance.
        expect(() => swiper.slideTo(0)).toThrow(/speed/);
        expect(liveSwiper(swiper)).toBeNull();
    });
});

// App keeps one Swiper instance in state for whichever layout is mounted. A layout
// switch (phone rotation, or the error panel's Retry) unmounts that Swiper, and
// Swiper's destroy() strips the instance's params. App still hands the destroyed
// object to the next layout until its own Swiper reports in, so calling slideTo on it
// throws "Cannot read properties of undefined (reading 'speed')" (TW-BUG-0001).
// Callers use this to ignore a destroyed instance instead of calling into it.
export const liveSwiper = swiper => (
    swiper && !swiper.destroyed && swiper.params ? swiper : null
);

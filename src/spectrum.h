/* The EQ page's spectrum: a 2048-point FFT of the output (L+R), spread over blocks so no block pays for it all,
 * read out as one level per screen column (dBFS: a 0 dBFS sine reads about 0). sp_start() takes the snapshot;
 * the passes then run 3 per sp_feed() call and the columns in the call after; sp_ready() says a reading is waiting. */
#ifndef SPECTRUM_H
#define SPECTRUM_H

typedef struct Spectrum Spectrum;

Spectrum *sp_create(float sample_rate, int ncols, float f_lo, float f_hi);   /* columns spaced evenly in log f */
void sp_destroy(Spectrum *s);
void sp_feed(Spectrum *s, const float *l, const float *r, int n);
int sp_start(Spectrum *s);                         /* 0 while the last one is still being worked out */
int sp_ready(const Spectrum *s);
void sp_read(Spectrum *s, float *col_db);          /* the reading, ncols values; clears sp_ready */

#endif

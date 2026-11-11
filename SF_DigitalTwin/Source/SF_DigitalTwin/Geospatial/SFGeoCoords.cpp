#include "SFGeoCoords.h"
#include <cmath>

namespace {
	// GRS80 (NAD83) ellipsoid, UTM zone 10N: central meridian -123, k0 0.9996, FE 500000.
	constexpr double A = 6378137.0, F = 1.0 / 298.257222101, K0 = 0.9996, FE = 500000.0, LON0 = -123.0;
	struct FSeries { double n, Ahat, a[3], b[3]; };
	FSeries MakeSeries() {
		FSeries S; const double n = F / (2.0 - F); S.n = n;
		const double n2 = n*n, n3 = n2*n;
		S.Ahat = A / (1.0 + n) * (1.0 + n2/4.0 + n2*n2/64.0);
		S.a[0] = n/2 - 2*n2/3 + 5*n3/16;       S.a[1] = 13*n2/48 - 3*n3/5;       S.a[2] = 61*n3/240;
		S.b[0] = n/2 - 2*n2/3 + 37*n3/96;      S.b[1] = n2/48 + n3/15;           S.b[2] = 17*n3/480;
		return S;
	}
}

void USFGeoCoords::LonLatToUTM10(double LonDeg, double LatDeg, double& E, double& N) {
	static const FSeries S = MakeSeries();
	const double phi = FMath::DegreesToRadians(LatDeg), lam = FMath::DegreesToRadians(LonDeg - LON0);
	const double e = FMath::Sqrt(F * (2.0 - F));
	const double t = FMath::Sinh(std::atanh(FMath::Sin(phi)) - e * std::atanh(e * FMath::Sin(phi)));
	const double xi = FMath::Atan2(t, FMath::Cos(lam));
	const double eta = std::atanh(FMath::Sin(lam) / FMath::Sqrt(1.0 + t*t));
	double xs = xi, es = eta;
	for (int j = 1; j <= 3; ++j) {
		xs += S.a[j-1] * FMath::Sin(2*j*xi) * FMath::Cosh(2*j*eta);
		es += S.a[j-1] * FMath::Cos(2*j*xi) * FMath::Sinh(2*j*eta);
	}
	E = FE + K0 * S.Ahat * es;
	N = K0 * S.Ahat * xs;
}

void USFGeoCoords::UTM10ToLonLat(double E, double N, double& LonDeg, double& LatDeg) {
	static const FSeries S = MakeSeries();
	const double xi = N / (K0 * S.Ahat), eta = (E - FE) / (K0 * S.Ahat);
	double xp = xi, ep = eta;
	for (int j = 1; j <= 3; ++j) {
		xp -= S.b[j-1] * FMath::Sin(2*j*xi) * FMath::Cosh(2*j*eta);
		ep -= S.b[j-1] * FMath::Cos(2*j*xi) * FMath::Sinh(2*j*eta);
	}
	const double chi = FMath::Asin(FMath::Sin(xp) / FMath::Cosh(ep));
	const double e = FMath::Sqrt(F * (2.0 - F));
	// Invert the conformal latitude by fixed-point iteration.
	double phi = chi;
	for (int i = 0; i < 8; ++i) phi = FMath::Asin(FMath::Tanh(std::atanh(FMath::Sin(chi)) + e * std::atanh(e * FMath::Sin(phi))));
	LatDeg = FMath::RadiansToDegrees(phi);
	LonDeg = LON0 + FMath::RadiansToDegrees(FMath::Atan2(FMath::Sinh(ep), FMath::Cos(xp)));
}

FVector USFGeoCoords::CityMetersToUnreal(double X, double Y, double Z) { return FVector(X * 100.0, -Y * 100.0, Z * 100.0); }

FVector USFGeoCoords::LonLatHeightToUnreal(double Lon, double Lat, double H) {
	double E, N; LonLatToUTM10(Lon, Lat, E, N);
	return CityMetersToUnreal(E - OriginE, N - OriginN, H);
}

void USFGeoCoords::UnrealToLonLatHeight(const FVector& L, double& Lon, double& Lat, double& H) {
	UTM10ToLonLat(OriginE + L.X / 100.0, OriginN - L.Y / 100.0, Lon, Lat);
	H = L.Z / 100.0;
}

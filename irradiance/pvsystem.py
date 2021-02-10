import pandas as pd
import numpy as np
from spa_delft import solar_position, solar_position_vectorized
import time
import requests
from requests.exceptions import HTTPError


class PVSystem:
    """The class represents a pv system array and its general attributes.

    Args :
    - latitude, longitude : decimal coordinates of system's location
    - elevation : distance aboves sea level

    - surface_azimuth
    - surface_tilt

    A surface facing south has an array azimuth of 180 deg.
    Surface tilt is defined as the angle from horizontal.
    Azimuth angle convention is defined as degrees east of north (e.g. North = 0, East = 90, West = 270).
    Array azimuth is defined as the horizontal normal vector from the array surface.

    """

    def __init__(
        self,
        name,
        latitude,
        longitude,
        elevation=0,
        surface_azimuth=180,
        surface_tilt=0,
    ):

        self.name = name
        self.lat = latitude
        self.lon = longitude
        self.elev = elevation
        self.surface_azimuth = surface_azimuth
        self.surface_tilt = surface_tilt

    def __repr__(self):

        attrs = [
            self.name,
            self.lat,
            self.lon,
            self.surface_azimuth,
            self.surface_tilt,
        ]
        return "PV System '{}' at Lat {} Lon {}. Array azimuth: {} tilt: {}".format(
            *attrs
        )


class Irradiance:
    """The irradiance Class represents the irradiance profiles and some
    of their conversion methods in order to obtain the POA Irradiance"""

    def __init__(
        self,
        pvsystem,
        times,
    ):
        # check if times arrays is datetimeindex
        if not isinstance(times, pd.DatetimeIndex):
            print("warning times is not datetime, ")
            try:
                times = pd.DatetimeIndex(times)
            except (TypeError, ValueError):
                times = pd.DatetimeIndex(
                    [
                        times,
                    ]
                )

        # if localized, convert to UTC. otherwise, assume UTC.
        try:
            print(times[0])
            times = times.tz_convert("UTC")
            print(times[0])
        except TypeError:
            times = times

        # if index (times) is not closed to left then drop last value.
        if len(times) == 8761:
            times = times[:8760]

        self.times = times
        self.lat = pvsystem.lat
        self.lon = pvsystem.lon
        self.elev = pvsystem.elev
        self.surface_azimuth = pvsystem.surface_azimuth
        self.surface_tilt = pvsystem.surface_tilt
        self.pvsystem = pvsystem

        self.solar_pos = None
        self.aoi = None
        self.tmy = None

    def read_TMY_file():
        """ "read the standard components GHI, DNI, DHI."""

    def get_TMY_file(self):
        """uses pvgis webservice to create a Typical Meteorological Year file
        for the location.


        Returns :
        - Dataframe instance consisting of 1 year (or several years) of hourly
        data,  with the following columns:

            Date & time (UTC for normal CSV, local timezone time
            T2m [°C] - Dry bulb (air) temperature.
            RH [%] -  Relative Humidity.
            G(h) [W/m2] - Global horizontal irradiance.
            Gb(n) [W/m2] - Direct (beam) irradiance.
            Gd(h) [W/m2] - Diffuse horizontal irradiance.
            IR(h) [W/m2] - Infrared radiation downwards.
            WS10m [m/s] - Windspeed.
            WD10m [°] - Wind direction.
            SP [Pa] - Surface (air) pressure.


        read more about TMY files
        https://ec.europa.eu/jrc/en/PVGIS/tools/tmy
        """

        url = "https://re.jrc.ec.europa.eu/api/tmy"
        params = {
            "lat": self.lat,
            "lon": self.lon,
            "startyear": 2006,
            "endyear": 2015,
            "outputformat": "json",  # csv, json, epw
        }

        start = time.time()

        try:
            r = requests.get(url, params=params)

            # If the respons was successful, no Exception will be raised
            r.raise_for_status()

        except HTTPError as http_err:
            print(f"HTTP error occurred: {http_err}")

        except Exception as err:
            print(f"Other error occurred: {err}")

        else:
            print("get_TMY_file: done in {:.2f} seconds.".format(time.time() - start))

            tmy_json = r.json()

            df_r = pd.DataFrame.from_dict(data=tmy_json["outputs"]["tmy_hourly"])

            df_tmy = df_r[["time(UTC)", "G(h)", "Gb(n)", "Gd(h)"]].copy()
            df_tmy.set_index(self.times, inplace=True)

            df_tmy.columns = ["time_pvgis", "GHI", "DNI", "DHI"]

            # df_tmy.drop(columns=["IR(h)", "WS10m", "WD10m", "SP"], axis=1, inplace=True)
            self.tmy = df_tmy

            return df_tmy

    def get_solar_pos_v(self):
        """
        Calculates the position of the sun relative to an observer on the
        surface of the Earth.
        The convention used to describe solar positions includes the parameters :
        - Zenith Angle : measured from observer's zenith (observers plane normal).
        - Azimuth Angle : measured in relation to North.
        - Solar Elevation Angle : measured up from the horizon (90deg - Zenith Angle).

        """

        start = time.time()
        print("calculating sun positions")
        self.solar_pos = solar_position_vectorized(self.times, self.lat, self.lon)
        # print(self.solar_pos)
        print("get_solar_pos_v : done in", time.time() - start)

    def get_aoi(self):
        """Calculates the angle of incidence between
        the Sun's rays and the surface of the PV Array.

        Args :
        sun_azimuth
        sun_zenith

        Return :

        """
        df_aoi = pd.DataFrame(index=self.solar_pos.index, columns=["aoi"])

        theta_A = np.radians(self.solar_pos["solar_azimuth"])  # azimuth
        theta_Z = np.radians(self.solar_pos["solar_zenith"])  # zenith
        theta_T = np.radians(self.surface_tilt)  # surface tilt
        theta_A_array = np.radians(self.surface_azimuth)  # surface azimuth

        c_zenith_cos = np.cos(theta_Z) * np.cos(theta_T)
        c_zenith_sin = (
            np.sin(theta_Z) * np.sin(theta_T) * np.cos(theta_A - theta_A_array)
        )

        df_aoi["aoi"] = np.degrees(np.arccos(c_zenith_cos + c_zenith_sin))
        self.aoi = df_aoi

        return df_aoi

    def get_poa_irradiance(self):
        """Calculates plane-of-array irradiance"""

        df_poa = pd.DataFrame(
            index=self.times, columns=["E_POA", "E_b_poa", "E_g_poa", "E_d_poa"]
        )

        # The plane of array (POA) beam component of irradiance is calculated
        # by adjusting the direct normal irradiance by the angle of incidence.

        aoi = self.aoi["aoi"]
        ghi = self.tmy["GHI"]
        dni = self.tmy["DNI"]
        dhi = self.tmy["DHI"]  # TODO : use
        albedo = 0.16  # Urban environement is 0.14 - 0.22

        # POA Beam component
        df_poa["E_b_poa"] = dni * np.cos(np.radians(aoi))

        # POA Ground component
        df_poa["E_g_poa"] = (
            ghi * albedo * ((1 - np.cos(np.radians(self.surface_tilt))) / 2)
        )

        # POA Sky Diffuse component
        E_d_iso = dhi * ((1 + np.cos(np.radians(self.surface_tilt))) / 2)
        E_d_correction = ghi * (
            (
                0.012
                * self.solar_pos["solar_zenith"]
                * (1 - np.cos(np.radians(self.surface_tilt)))
            )
            / 2
        )

        df_poa["E_d_poa"] = E_d_iso + E_d_correction

        # POA Irradiance total
        df_poa["E_POA"] = df_poa["E_b_poa"] + df_poa["E_g_poa"] + df_poa["E_d_poa"]

        return df_poa

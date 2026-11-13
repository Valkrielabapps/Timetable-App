package com.timetablz.app.data

import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

/** The Timetablz API (the website's backend), as Retrofit sees it. Base: https://timetablz.com/api/ */
interface TimetablzApi {
    @POST("auth/login") suspend fun login(@Body body: LoginRequest): TokenResponse
    @POST("auth/google") suspend fun google(@Body body: GoogleRequest): TokenResponse
    @GET("auth/me") suspend fun me(): User
    @POST("auth/accept-terms") suspend fun acceptTerms(@Body body: TermsRequest): User

    @GET("schools") suspend fun schools(): List<School>
    @GET("periods") suspend fun periods(@Query("school_id") schoolId: Int): List<Period>
    @GET("class-groups") suspend fun classGroups(@Query("school_id") schoolId: Int): List<ClassGroup>
    @GET("teachers") suspend fun teachers(@Query("school_id") schoolId: Int): List<Teacher>
    @GET("timetables") suspend fun timetables(@Query("school_id") schoolId: Int): List<TimetableSummary>
    @GET("timetables/{id}") suspend fun timetable(@Path("id") id: Int): Timetable

    @GET("schools/{id}/substitutions") suspend fun covers(@Path("id") schoolId: Int): List<CoverLogDto>
    @POST("schools/{id}/substitutions") suspend fun saveCover(@Path("id") schoolId: Int, @Body body: SaveCoverRequest): CoverLogDto
    @GET("schools/{id}/substitutions/summary") suspend fun summary(@Path("id") schoolId: Int, @Query("date") date: String): SummaryDto
    @POST("schools/{id}/substitutions/notify") suspend fun notify(@Path("id") schoolId: Int, @Body body: NotifyRequest): NotifyDto
}
